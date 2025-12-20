import httpx
import asyncio
import websockets
from starlette.websockets import WebSocketState
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


from settings import DOC_SERVICE_URL, COLLAB_HUB_URL

app = FastAPI(
    title="Conspektor API Gateway",
    version="0.1.0",
    description="API Gateway for Conspektor (documents & collaboration)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

async def forward_request_to_doc_service(method: str, path: str, json: dict | None = None):
    """Проброс запроса в Document Service."""
    url = f"{DOC_SERVICE_URL}{path}"
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "DELETE" and json is None:
                resp = await client.request(method, url, timeout=30.0)
            else:
                resp = await client.request(method, url, json=json, timeout=30.0)
            
        except httpx.RequestError as e:
            print(f"[gateway] Document Service unavailable: {e}")
            raise HTTPException(status_code=502, detail=f"Document Service unavailable: {e}") from e

    return JSONResponse(
        status_code=resp.status_code,
        content=resp.json() if resp.content else None,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

# Endpoints

@app.get("/documents")
async def get_documents():
    """
    Получить список документов.
    Проксируется в Document Service: GET /documents
    """
    return await forward_request_to_doc_service("GET", "/documents")


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """
    Получить один документ.
    Проксируется в Document Service: GET /documents/{doc_id}
    """
    return await forward_request_to_doc_service("GET", f"/documents/{doc_id}")

@app.get("/users/username/{username}")
async def get_user_by_username(username: str):
    """Получить пользователя по username"""
    return await forward_request_to_doc_service("GET", f"/users/username/{username}")

@app.get("/documents/user/{user_id}")
async def get_user_documents(user_id: str):
    """Получить документы пользователя по user_id"""
    return await forward_request_to_doc_service("GET", f"/documents/user/{user_id}")

@app.get("/documents/shared/{user_id}")
async def get_shared_documents(user_id: str):
    """
    Получить shared документы пользователя.
    Проксируется в Document Service: GET /documents/shared/{user_id}
    """
    return await forward_request_to_doc_service("GET", f"/documents/shared/{user_id}")

@app.put("/documents/{doc_id}")
async def update_document(doc_id: str, body: dict):
    """
    Обновить документ целиком (content, title, ...).
    Проксируется в Document Service: PUT /documents/{doc_id}
    """
    return await forward_request_to_doc_service("PUT", f"/documents/{doc_id}", json=body)

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """
    Удалить документ.
    Проксируется в Document Service: DELETE /documents/{doc_id}
    """
    return await forward_request_to_doc_service("DELETE", f"/documents/{doc_id}")

@app.post("/documents")
async def create_document(body: dict):
    """
    Создать новый документ.
    Проксируется в Document Service: POST /documents
    """
    return await forward_request_to_doc_service("POST", "/documents", json=body)

@app.websocket("/ws/documents/{doc_id}")
async def ws_docs(websocket: WebSocket, doc_id: str):
    """
    клиент <-> API Gateway <-> Collaboration Hub
    """
    await websocket.accept()

    token = websocket.query_params.get("token")
    if token is None:
        await websocket.send_json({"type": "error", "message": "Missing token"})
        await websocket.close()
        return

    if COLLAB_HUB_URL.startswith("http://"):
        hub_ws_url = COLLAB_HUB_URL.replace("http://", "ws://", 1)
    elif COLLAB_HUB_URL.startswith("https://"):
        hub_ws_url = COLLAB_HUB_URL.replace("https://", "wss://", 1)
    else:
        hub_ws_url = COLLAB_HUB_URL

    hub_url = f"{hub_ws_url.rstrip('/')}/ws/documents/{doc_id}?token={token}"

    try:
        async with websockets.connect(hub_url) as hub_ws:
            async def client_to_hub():
                try:
                    while True:
                        msg = await websocket.receive_text()
                        await hub_ws.send(msg)
                except WebSocketDisconnect:
                    await hub_ws.close()
                except Exception:
                    await hub_ws.close()

            async def hub_to_client():
                try:
                    async for msg in hub_ws:
                        await websocket.send_text(msg)
                except Exception:
                    if websocket.application_state != WebSocketState.DISCONNECTED:
                        await websocket.close()

            await asyncio.gather(client_to_hub(), hub_to_client())

    except Exception as e:
        print(f"[gateway ws proxy error] {e}")
        if websocket.application_state != WebSocketState.DISCONNECTED:
            await websocket.close()

@app.post("/documents/{doc_id}/collaborators")
async def add_collaborators(doc_id: str, body: dict):
    return await forward_request_to_doc_service(
        "POST", 
        f"/documents/{doc_id}/collaborators", 
        json=body
    )