from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import uuid

from database import db
from cache import cache

app = FastAPI(title="Document Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://front-end:8080", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await db.connect()

@app.on_event("shutdown")
async def shutdown():
    await db.close()

# ===== ПОЛЬЗОВАТЕЛИ =====

@app.get("/users/username/{username}")
async def get_user_by_username_endpoint(username: str):
    user = await db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/users/{user_id}")
async def get_user_by_id_endpoint(user_id: str):
    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/users")
async def create_user(user_data: dict):
    email = user_data.get("email")
    username = user_data.get("username")
    
    if not email or not username:
        raise HTTPException(status_code=400, detail="Email and username are required")
    
    user = await db.create_user(email, username)
    if not user:
        raise HTTPException(status_code=400, detail="User already exists or invalid data")
    
    return user

# ===== ДОКУМЕНТЫ =====

@app.get("/documents", response_model=List[Dict[str, Any]])
async def get_documents():
    try:
        documents = await db.get_documents()
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/documents/{doc_id}")
async def get_document(doc_id: str, user_id: str):
    """Получить документ по ID"""
    has_access = await db.check_permission(user_id, doc_id, 'view')
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")
    
    document = await db.get_document(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

@app.get("/documents/user/{user_id}")
async def get_user_documents(user_id: str):
    """Получить все документы пользователя"""
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
    owner_id = document_data.get("owner_id")
    
    if not owner_id:
        raise HTTPException(status_code=400, detail="Owner ID is required")
    
    user = await db.get_user_by_id(owner_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        document = await db.create_document(title, content, owner_id)
        return document
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")

@app.put("/documents/{doc_id}")
async def update_document(doc_id: str, document_data: dict):
    """Обновить документ"""
    title = document_data.get("title")
    content = document_data.get("content")
    user_id = document_data.get("user_id")
    
    if title is None or content is None or not user_id:
        raise HTTPException(status_code=400, detail="Title, content and user_id are required")

    has_access = await db.check_permission(user_id, doc_id, 'edit')
    if not has_access:
        raise HTTPException(status_code=403, detail="Edit permission required")
    
    document = await db.update_document(doc_id, title, content)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user_id: str):
    """Удалить документ (только владелец или системный администратор)"""
    can_delete = await db.check_document_admin(user_id, doc_id)
    if not can_delete:
        is_system_admin = await db.check_system_admin(user_id)
        if not is_system_admin:
            raise HTTPException(
                status_code=403, 
                detail="Only document owner/admin or system administrator can delete document"
            )
    
    success = await db.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted successfully"}

# ===== ПРАВА И РОЛИ =====

@app.post("/users/{user_id}/role")
async def set_user_role(user_id: str, role_data: dict, current_user_id: str):
    """Установить системную роль пользователя (только для админов)"""
    is_admin = await db.check_system_admin(current_user_id)
    if not is_admin:
        raise HTTPException(status_code=403, detail="System admin permission required")
    
    role = role_data.get("role")
    if role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role. Allowed: admin, user")
    
    success = await db.set_user_role(user_id, role, current_user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set role")
    
    return {"message": "Role updated successfully"}

@app.get("/documents/{doc_id}/collaborators")
async def get_document_collaborators(doc_id: str, user_id: str):
    """Получить список всех пользователей с доступом к документу"""
    has_access = await db.check_permission(user_id, doc_id, 'view')
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")
    
    collaborators = await db.get_document_collaborators(doc_id)
    return collaborators

@app.post("/documents/{doc_id}/permissions/{target_user_id}")
async def set_document_permission(doc_id: str, target_user_id: str, permission_data: dict, current_user_id: str):
    """Установить права доступа к документу"""
    permission = permission_data.get("permission")
    if permission not in ["view", "comment", "edit", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid permission")
    
    can_manage = await db.check_document_admin(current_user_id, doc_id)
    if not can_manage:
        is_system_admin = await db.check_system_admin(current_user_id)
        if not is_system_admin:
            raise HTTPException(status_code=403, detail="Document admin or system admin permission required")
    
    success = await db.set_document_permission(doc_id, target_user_id, permission)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set permission")
    
    return {"message": "Permission updated successfully"}

@app.delete("/documents/{doc_id}/permissions/{target_user_id}")
async def remove_document_permission(doc_id: str, target_user_id: str, current_user_id: str):
    """Удалить права доступа к документу"""
    can_manage = await db.check_document_admin(current_user_id, doc_id)
    if not can_manage:
        is_system_admin = await db.check_system_admin(current_user_id)
        if not is_system_admin:
            raise HTTPException(status_code=403, detail="Document admin or system admin permission required")
    
    if target_user_id == current_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove your own permissions")
    
    success = await db.remove_document_permission(doc_id, target_user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove permission")
    
    return {"message": "Permission removed successfully"}

@app.post("/documents/{doc_id}/transfer/{new_owner_id}")
async def transfer_document_ownership(doc_id: str, new_owner_id: str, current_user_id: str):
    """Передать владение документом другому пользователю"""
    is_owner = await db.check_document_ownership(current_user_id, doc_id)
    if not is_owner:
        raise HTTPException(status_code=403, detail="Only document owner can transfer ownership")

    new_owner = await db.get_user_by_id(new_owner_id)
    if not new_owner:
        raise HTTPException(status_code=404, detail="New owner not found")
    
    success = await db.transfer_document_ownership(doc_id, new_owner_id, current_user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to transfer ownership")
    
    return {"message": "Ownership transferred successfully"}

@app.get("/documents/{doc_id}/permissions/check")
async def check_document_permission(doc_id: str, user_id: str, permission: str = "view"):
    """Проверить права доступа пользователя к документу"""
    has_access = await db.check_permission(user_id, doc_id, permission)
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {"has_access": True, "permission": permission}

@app.post("/documents/{doc_id}/public")
async def toggle_public_document(doc_id: str, public_data: dict, user_id: str):
    """Сделать документ публичным/приватным (только владелец или администратор документа)"""
    is_public = public_data.get("is_public", False)
    
    can_manage = await db.check_document_admin(user_id, doc_id)
    if not can_manage:
        raise HTTPException(status_code=403, detail="Only document admin can change visibility")
    
    async with db.pool.acquire() as conn:
        await conn.execute("""
            UPDATE documents 
            SET is_public = $1, updated_at = CURRENT_TIMESTAMP 
            WHERE id = $2
        """, is_public, doc_id)

    cache.invalidate_document(doc_id)
    await cache.invalidate_document_permissions(doc_id)
    
    return {"message": f"Document is now {'public' if is_public else 'private'}"}

# ===== СИСТЕМНЫЕ КОМАНДЫ =====

@app.get("/health")
async def health_check():
    try:
        await db.pool.fetch("SELECT 1")
        redis_healthy = await cache.health_check()
        
        return {
            "status": "healthy",
            "service": "document-service",
            "postgresql": "connected",
            "redis": "connected" if redis_healthy else "disconnected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

@app.get("/system/admin-check/{user_id}")
async def check_system_admin(user_id: str):
    """Проверить, является ли пользователь системным администратором"""
    is_admin = await db.check_system_admin(user_id)
    return {"is_system_admin": is_admin}

@app.get("/system/document-admin-check/{doc_id}/{user_id}")
async def check_document_admin(doc_id: str, user_id: str):
    """Проверить, имеет ли пользователь права администратора на документ"""
    is_doc_admin = await db.check_document_admin(user_id, doc_id)
    return {"is_document_admin": is_doc_admin, "is_owner": await db.check_document_ownership(user_id, doc_id)}