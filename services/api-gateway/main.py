from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import httpx

from settings import DOC_SERVICE_URL

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


# Заглушка
@app.websocket("/ws/documents/{doc_id}")
async def ws_docs(websocket: WebSocket, doc_id: int):
    await websocket.accept()
    try:
        await websocket.send_json({"type": "info", "message": "WS connected (placeholder)"})
        while True:
            data = await websocket.receive_text()
            print("WS received:", data)
    except WebSocketDisconnect:
        print("Client disconnected")

@app.get("/health")
async def health_check():
    """Проверка, что gateway жив."""
    return {"status": "ok", "service": "api-gateway"}
