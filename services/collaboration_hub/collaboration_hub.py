import os
import asyncio
import json
from typing import Dict, Set, Optional
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState
from fastapi.responses import JSONResponse
import y_py as Y

DOCUMENT_SERVICE_URL = os.getenv("DOCUMENT_SERVICE_URL", "http://localhost:8001")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8003")
MESSAGE_BROKER_URL = os.getenv("MESSAGE_BROKER_URL", "")
SAVE_DEBOUNCE_SECONDS = float(os.getenv("SAVE_DEBOUNCE_SECONDS", "2.0"))

app = FastAPI(title="Collaboration Hub with CRDT")


class DocumentRoom:
    """
    Комната документа с CRDT-синхронизацией через Yjs.
    Использует Y.Doc для автоматического разрешения конфликтов.
    """
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.clients: Set[WebSocket] = set()
        self.ydoc = Y.YDoc()
        self.yxml = self.ydoc.get_xml("content")
        self.lock = asyncio.Lock()
        self._save_task: Optional[asyncio.Task] = None
        self._last_change_ts: Optional[float] = None
        self._initialized = False

    async def initialize_from_document_service(self, initial_content: str):
        """Инициализация CRDT документа из Document Service"""
        if not self._initialized:
            with self.ydoc.begin_transaction() as txn:
                self.yxml.delete_range(txn, 0, self.yxml.length(txn))
                self.yxml.insert(txn, 0, initial_content)
            self._initialized = True

    def get_content(self) -> str:
        """Получить текущее содержимое документа"""
        return self.yxml.to_xml()

    def apply_update(self, update: bytes) -> bytes:
        """
        Применить обновление от клиента к CRDT документу.
        Возвращает state vector для синхронизации.
        """
        Y.apply_update(self.ydoc, update)
        return Y.encode_state_as_update(self.ydoc)

    def get_state_vector(self) -> bytes:
        """Получить текущий state vector документа"""
        return Y.encode_state_vector(self.ydoc)

    def get_full_update(self) -> bytes:
        """Получить полное обновление документа"""
        return Y.encode_state_as_update(self.ydoc)

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
                    content = self.get_content()
                    await save_document_to_document_service(self.doc_id, content)
                    print(f"[save] doc={self.doc_id} saved successfully")
                except Exception as e:
                    print(f"[save error] doc={self.doc_id} err={e}")
                break


rooms: Dict[str, DocumentRoom] = {}


async def verify_token_for_document(token: str, doc_id: str) -> bool:
    """Проверка токена для доступа к документу"""
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
            doc = await fetch_document_from_document_service(doc_id)
            title = doc.get("title", "Untitled") if doc else "Untitled"
            
            payload = {"title": title, "content": content}
            r = await client.put(url, json=payload)
            return r.status_code == 200
        except Exception as e:
            print(f"[save doc error] {e}")
            return False


async def publish_event_to_broker(doc_id: str, event: dict):
    """Отправка события редактирования в Message Broker"""
    if not MESSAGE_BROKER_URL:
        print(f"[broker] Message Broker URL not configured, skipping event publish")
        return
    
    url = MESSAGE_BROKER_URL.rstrip("/") + "/events"
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            payload = {
                "doc_id": doc_id,
                "event_type": event.get("type", "update"),
                "timestamp": asyncio.get_event_loop().time(),
                "data": event
            }
            await client.post(url, json=payload)
            print(f"[broker] Event published for doc={doc_id}")
        except Exception as e:
            print(f"[broker publish error] {e}")


@app.websocket("/ws/documents/{doc_id}")
async def ws_document_endpoint(websocket: WebSocket, doc_id: str, token: Optional[str] = Query(None)):
    """
    WebSocket для работы с документом с CRDT-синхронизацией:
    - Отправка initial state (state vector + full update)
    - Получение CRDT updates от клиента
    - Рассылка updates другим клиентам
    - Автоматическое разрешение конфликтов через Yjs
    - Отложенное сохранение (debounce)
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
        if not room._initialized:
            doc = await fetch_document_from_document_service(doc_id)
            if doc is None:
                await websocket.send_json({"type": "error", "message": "Document not found"})
                room.clients.discard(websocket)
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            if isinstance(doc, list) and len(doc) > 0:
                doc = doc[0]
            
            initial_content = doc.get("content", "")
            await room.initialize_from_document_service(initial_content)
            print(f"[init] doc={doc_id} initialized with content length={len(initial_content)}")

    try:
        state_vector = room.get_state_vector()
        full_update = room.get_full_update()
        
        await websocket.send_json({
            "type": "sync",
            "stateVector": state_vector.hex(),
            "update": full_update.hex()
        })
        print(f"[sync] Sent initial sync to client for doc={doc_id}")
    except Exception as e:
        print(f"[sync error] {e}")
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
            
            if mtype == "update":
                # Получили CRDT update от клиента
                update_hex = msg.get("update", "")
                if not update_hex:
                    await websocket.send_json({"type": "error", "message": "Missing update data"})
                    continue
                
                try:
                    update_bytes = bytes.fromhex(update_hex)
                    
                    async with room.lock:
                        # Применяем update к CRDT документу
                        room.apply_update(update_bytes)
                        
                        # Рассылаем update всем остальным клиентам
                        payload = {
                            "type": "update",
                            "update": update_hex
                        }
                        await broadcast_to_room(room, payload, exclude=websocket)
                        
                        # Публикуем событие в Message Broker
                        await publish_event_to_broker(doc_id, {
                            "type": "crdt_update",
                            "update": update_hex,
                            "content_preview": room.get_content()[:100]
                        })
                        
                        # Планируем сохранение
                        await room.schedule_save()
                        
                    print(f"[update] Applied CRDT update for doc={doc_id}, content length={len(room.get_content())}")
                    
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": f"Invalid update format: {e}"})
                except Exception as e:
                    print(f"[update error] {e}")
                    await websocket.send_json({"type": "error", "message": f"Failed to apply update: {e}"})
                    
            elif mtype == "sync_request":
                # Клиент запрашивает синхронизацию
                try:
                    state_vector_hex = msg.get("stateVector", "")
                    if state_vector_hex:
                        client_state = bytes.fromhex(state_vector_hex)
                        # Вычисляем diff между состояниями
                        diff_update = Y.encode_state_as_update(room.ydoc, client_state)
                    else:
                        # Если state vector не предоставлен, отправляем полное обновление
                        diff_update = room.get_full_update()
                    
                    await websocket.send_json({
                        "type": "sync",
                        "update": diff_update.hex()
                    })
                    print(f"[sync] Sent sync response for doc={doc_id}")
                except Exception as e:
                    print(f"[sync error] {e}")
                    await websocket.send_json({"type": "error", "message": f"Sync failed: {e}"})
                    
            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown type {mtype}"})

    except WebSocketDisconnect:
        print(f"[disconnect] Client disconnected from doc={doc_id}")
    except Exception as e:
        print(f"[ws error] {e}")
    finally:
        room.clients.discard(websocket)
        if not room.clients:
            # Последний клиент отключился - сохраняем документ
            if room._initialized:
                content = room.get_content()
                asyncio.create_task(save_document_to_document_service(room.doc_id, content))
                print(f"[cleanup] Saving doc={doc_id} before cleanup")
            rooms.pop(doc_id, None)
            print(f"[cleanup] Room for doc={doc_id} cleaned up")


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
        except Exception as e:
            print(f"[broadcast error] {e}")
            dead.add(ws)
    for d in dead:
        room.clients.discard(d)


@app.get("/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "rooms": len(rooms),
        "crdt_enabled": True,
        "message_broker_configured": bool(MESSAGE_BROKER_URL)
    })


@app.get("/rooms/{doc_id}/info")
async def room_info(doc_id: str):
    """Получить информацию о комнате документа"""
    room = rooms.get(doc_id)
    if not room:
        return JSONResponse({"error": "Room not found"}, status_code=404)
    
    return JSONResponse({
        "doc_id": doc_id,
        "clients_count": len(room.clients),
        "content_length": len(room.get_content()),
        "initialized": room._initialized
    })