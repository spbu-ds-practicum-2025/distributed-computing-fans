from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
import httpx
from typing import List, Dict, Any

from database import db

app = FastAPI(title="Document Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def message_broker_poller():
    """Фоновый процесс для чтения событий из Message Broker"""
    broker_url = os.getenv("MESSAGE_BROKER_URL", "http://message-broker:8003")
    client_id = "document-service-1"
    last_event_id = -1
    
    print(f"[Broker] Starting poller for {broker_url}")
    
    while True:
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                response = await client.get(
                    f"{broker_url}/events",
                    params={
                        "client_id": client_id,
                        "last_event_id": last_event_id
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    events = data.get("events", [])
                    last_event_id = data.get("last_event_id", last_event_id)
                    
                    for event in events:
                        await process_broker_event(event)
                        
                elif response.status_code >= 400:
                    print(f"[Broker] Error {response.status_code}, retrying in 5s")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            print(f"[Broker Poller Error] {e}")
            await asyncio.sleep(5)

async def process_broker_event(event: dict):
    """Обработка события из брокера"""
    try:
        doc_id = event.get("document_id")
        content = event.get("content", "")
        
        if doc_id and content:
            print(f"[Broker] Processing event for doc {doc_id}")
            
            title = "Обновлено через брокер"
            result = await db.update_document(doc_id, title, content)
            
            if result:
                print(f"[Broker] Document {doc_id} updated successfully")
            else:
                print(f"[Broker] Failed to update document {doc_id}")
                
    except Exception as e:
        print(f"[Broker Event Error] {e}")


@app.on_event("startup")
async def startup():
    """Подключение к БД при запуске"""
    await db.connect()
    asyncio.create_task(message_broker_poller())
    print("[Document Service] Message broker poller started")

@app.on_event("shutdown")
async def shutdown():
    """Отключение от БД при остановке"""
    await db.close()

# API Endpoints
@app.get("/documents", response_model=List[Dict[str, Any]])
async def get_documents():
    """Получить список всех документов"""
    try:
        documents = await db.get_documents()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Получить документ по ID"""
    document = await db.get_document(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

@app.get("/documents/shared/{user_id}")
async def get_shared_documents(user_id: str):
    """Получить документы, к которым пользователь имеет доступ через collaborator"""
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT d.id, d.title, d.content, d.owner_id, 
                       d.created_at, d.updated_at,
                       u.username as owner_username
                FROM documents d
                JOIN document_collaborators dc ON d.id = dc.document_id
                JOIN users u ON d.owner_id = u.id
                WHERE dc.user_id = $1
                ORDER BY d.updated_at DESC
            """, user_id)
            
            documents = [dict(row) for row in rows]
            return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/users/username/{username}")
async def get_user_by_username_endpoint(username: str):
    """Получить пользователя по username"""
    user = await db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/documents/user/{user_id}")
async def get_user_documents(user_id: str):
    """Получить документы пользователя"""
    try:
        documents = await db.get_user_documents(user_id)
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/documents")
async def create_document(document_data: dict):
    """Создать новый документ"""
    title = document_data.get("title", "Новый документ")
    content = document_data.get("content", "")
    username = document_data.get("username")

    try:
        
        if username:
            user = await db.get_user_by_username(username)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            owner_id = user["id"]
        else:
            owner_id = None

        document = await db.create_document(title, content, owner_id)
        return document
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")

@app.post("/documents/{doc_id}/collaborators")
async def add_collaborators(doc_id: str, request_data: dict):
    """Добавить collaborator к документу"""
    try:
        user_ids = request_data.get("user_ids", [])
        permission = request_data.get("permission", "edit")
        
        if not user_ids:
            raise HTTPException(status_code=400, detail="No users specified")
        
        results = []
        for user_id in user_ids:
            success = await db.add_collaborator(doc_id, user_id, permission)
            results.append({
                "user_id": user_id,
                "success": success
            })
        
        if any(r["success"] for r in results):
            return {
                "message": "Collaborators added successfully",
                "results": results
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to add collaborators")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add collaborators: {str(e)}")

@app.put("/documents/{doc_id}")
async def update_document(doc_id: str, document_data: dict):
    """Обновить документ"""
    title = document_data.get("title")
    content = document_data.get("content")
    
    if title is None or content is None:
        raise HTTPException(status_code=400, detail="Title and content are required")
    
    document = await db.update_document(doc_id, title, content)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Удалить документ"""
    success = await db.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted successfully"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await db.pool.fetch("SELECT 1")
        return {
            "status": "healthy",
            "service": "document-service",
            "database": "connected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")