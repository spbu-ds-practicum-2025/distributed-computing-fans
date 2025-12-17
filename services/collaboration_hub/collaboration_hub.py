
import os
import asyncio
import json
from typing import Dict, Set, Optional
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState
from fastapi.responses import JSONResponse

DOCUMENT_SERVICE_URL = os.getenv("DOCUMENT_SERVICE_URL", "http://localhost:8001")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8003")
MESSAGE_BROKER_URL = os.getenv("MESSAGE_BROKER_URL", "")
SAVE_DEBOUNCE_SECONDS = float(os.getenv("SAVE_DEBOUNCE_SECONDS", "2.0"))

app = FastAPI(title="Collaboration Hub (MVP)")


class DocumentRoom:
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.clients: Set[WebSocket] = set()
        self.content: Optional[str] = None
        self.lock = asyncio.Lock()
        self._save_task: Optional[asyncio.Task] = None
        self._last_change_ts: Optional[float] = None

    async def schedule_save(self):
        """Запускает отложенное сохранение"""
        self._last_change_ts = asyncio.get_event_loop().time()
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._debounced_save_loop())

    async def _debounced_save_loop(self):
        """
        Ждёт SAVE_DEBOUNCE_SECONDS после последнего изменения,
        затем сохраняет документ в Document Service
        """
        while True:
            await asyncio.sleep(SAVE_DEBOUNCE_SECONDS)
            elapsed = asyncio.get_event_loop().time() - (self._last_change_ts or 0)
            if elapsed >= SAVE_DEBOUNCE_SECONDS:
                try:
                    await save_document_to_document_service(self.doc_id, self.content or "")
                except Exception as e:
                    print(f"[save error] doc={self.doc_id} err={e}")
                break


rooms: Dict[str, DocumentRoom] = {}

# async def verify_token_for_document(token: str, doc_id: str) -> bool:
#     """Проверка токена в Auth Service для доступа к документу"""
#     if not AUTH_SERVICE_URL:
#         return True

#     url = f"{AUTH_SERVICE_URL.rstrip('/')}/verify?doc_id={doc_id}"
#     async with httpx.AsyncClient(timeout=5.0) as client:
#         try:
#             r = await client.post(url, json={"token": token})
#             return r.status_code == 200 and r.json().get("ok", True)
#         except Exception as e:
#             print(f"[auth error] {e}")
#             return False

async def verify_token_for_document(token: str, doc_id: str) -> bool:
    """Проверка токена для доступа к документу"""
    # В MVP отключаем проверку через Auth Service
    print(f"[auth] Skipping auth check for doc {doc_id} (MVP)")
    return True


async def fetch_document_from_document_service(doc_id: str) -> Optional[dict]:
    """
    Получает документ из Document Service.
    Возвращает JSON документа или None
    """
    url = f"{DOCUMENT_SERVICE_URL.rstrip('/')}/documents/{doc_id}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.json()
            else:
                return None
        except Exception as e:
            print(f"[fetch doc error] {e}")
            return None


async def save_document_to_document_service(doc_id: str, content: str) -> bool:
    """Сохраняет документ в Document Service"""
    url = f"{DOCUMENT_SERVICE_URL.rstrip('/')}/documents/{doc_id}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            payload = {"content": content}
            r = await client.put(url, json=payload)
            return r.status_code == 200
        except Exception as e:
            print(f"[save doc error] {e}")
            return False


async def publish_event_to_broker(doc_id: str, event: dict):
    """Отправка события редактирования в Message Broker"""
    if not MESSAGE_BROKER_URL:
        return
    url = MESSAGE_BROKER_URL.rstrip("/") + "/events"
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post(url, json={"doc_id": doc_id, "event": event})
        except Exception as e:
            print(f"[broker publish error] {e}")


@app.websocket("/ws/documents/{doc_id}")
async def ws_document_endpoint(websocket: WebSocket, doc_id: str, token: Optional[str] = Query(None)):
    """
    WebSocket для работы с документом:
    отправка initial состояния
    получение изменений от клиента
    рассылка обновлений другим клиентам
    отложенное сохранение (debounce)
    """
    await websocket.accept()

    if token is None:
        await websocket.send_json({"type": "error", "message": "Missing token. Provide ?token=... in WS URL."})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    authorized = await verify_token_for_document(token, doc_id)
    if not authorized:
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
   
    room = rooms.get(doc_id)
    if room is None:
        room = DocumentRoom(doc_id)
        rooms[doc_id] = room

    room.clients.add(websocket)

    async with room.lock:
        if room.content is None:
            doc = await fetch_document_from_document_service(doc_id)
            if doc is None:
                await websocket.send_json({"type": "error", "message": "Document not found"})
                room.clients.discard(websocket)
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            if isinstance(doc, list) and len(doc) > 0:
                doc = doc[0]
            room.content = doc.get("content", "")

    try:
        await websocket.send_json({"type": "initial", "content": room.content})
    except Exception:
        room.clients.discard(websocket)
        return

    try:
        while True:
            msg_text = await websocket.receive_text()
            try:
                msg = json.loads(msg_text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            if not isinstance(msg, dict) or "type" not in msg:
                await websocket.send_json({"type": "error", "message": "Invalid message format"})
                continue

            mtype = msg["type"]
            if mtype == "change":
                new_content = msg.get("content", "")
                async with room.lock:
                    room.content = new_content
                    payload = {"type": "update", "content": new_content}
                    await broadcast_to_room(room, payload, exclude=websocket)
                    await publish_event_to_broker(doc_id, {"type": "change", "content": new_content})
                    await room.schedule_save()
            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown type {mtype}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws error] {e}")
    finally:
        room.clients.discard(websocket)
        if not room.clients:
            if room.content is not None:
                asyncio.create_task(save_document_to_document_service(room.doc_id, room.content))
            rooms.pop(doc_id, None)


async def broadcast_to_room(room: DocumentRoom, payload: dict, exclude: Optional[WebSocket] = None):
    """Рассылка сообщений всем клиентам комнаты"""
    dead: Set[WebSocket] = set()
    data = json.dumps(payload)
    for ws in list(room.clients):
        if ws is exclude:
            continue
        try:
            if ws.application_state == WebSocketState.CONNECTED:
                await ws.send_text(data)
            else:
                dead.add(ws)
        except Exception:
            dead.add(ws)
    for d in dead:
        room.clients.discard(d)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "rooms": len(rooms)})
