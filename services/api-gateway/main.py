import httpx
import asyncio
import websockets
from starlette.websockets import WebSocketState
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def forward_request_to_doc_service(method: str, path: str, json: dict | None = None):
    """Проброс запроса в Document Service."""
    url = f"{DOC_SERVICE_URL}{path}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.request(method, url, json=json)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Document Service unavailable: {e}") from e

    return JSONResponse(
        status_code=resp.status_code,
        content=resp.json() if resp.content else None,
    )

# Endpoints

@app.get("/documents")
async def get_documents():
    """
    Получить список документов.
    Проксируется в Document Service: GET /documents
    """
    return await forward_request_to_doc_service("GET", "/documents")

    """
    Клиент прислал GET /documents
    Gateway вызвал forward_request_to_doc_service()
    Далее запрос ушёл в Document Service: GET http://localhost:8001/documents
    """


@app.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    """
    Получить один документ.
    Проксируется в Document Service: GET /documents/{doc_id}
    """
    return await forward_request_to_doc_service("GET", f"/documents/{doc_id}")


@app.put("/documents/{doc_id}")
async def update_document(doc_id: int, body: dict):
    """
    Обновить документ целиком (content, title, ...).
    Проксируется в Document Service: PUT /documents/{doc_id}
    """
    return await forward_request_to_doc_service("PUT", f"/documents/{doc_id}", json=body)

    """
    Клиент (Frontend) вызывает PUT /documents/1, посылая JSON с новым текстом документа.
    Gateway пересылает этот JSON в Document Service.
    Document Service обновляет PostgreSQL.
    """


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

    hub_url = f"{COLLAB_HUB_URL.rstrip('/')}/ws/documents/{doc_id}?token={token}"

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
