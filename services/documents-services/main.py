from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
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

@app.on_event("startup")
async def startup():
    """Подключение к БД при запуске"""
    await db.connect()

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