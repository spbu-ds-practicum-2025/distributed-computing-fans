import asyncpg
import os
from typing import List, Optional, Dict, Any
from cache import cache

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Установка соединения с PostgreSQL"""
        self.pool = await asyncpg.create_pool(
            dsn=os.getenv('DATABASE_URL'),
            min_size=1,
            max_size=10
        )

    async def close(self):
        """Закрытие соединения"""
        if self.pool:
            await self.pool.close()
    
    # ===== МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ =====
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Получить пользователя по username"""
        cached = await cache.get_user_by_username(username)
        if cached:
            return cached
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, email, username, role, created_at
                FROM users 
                WHERE username = $1
            """, username)
            
            if row:
                user = dict(row)
                await cache.set_user(user['id'], user)
                return user
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Получить пользователя по ID"""
        cached = await cache.get_user(user_id)
        if cached:
            return cached
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, email, username, role, created_at
                FROM users 
                WHERE id = $1
            """, user_id)
            
            if row:
                user = dict(row)
                await cache.set_user(user_id, user)
                return user
            return None
    
    async def create_user(self, email: str, username: str) -> Optional[Dict]:
        """Создать нового пользователя"""
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow("""
                    INSERT INTO users (email, username) 
                    VALUES ($1, $2)
                    RETURNING id, email, username, role, created_at
                """, email, username)
                
                if row:
                    user = dict(row)
                    await cache.set_user(user['id'], user)
                    return user
            except asyncpg.exceptions.UniqueViolationError:
                return None
            except Exception as e:
                print(f"Error creating user: {e}")
                return None
    
    # ===== ОСНОВНАЯ СИСТЕМА ПРОВЕРКИ ПРАВ =====
    
    async def check_permission(self, user_id: str, doc_id: str, required_permission: str = 'view') -> bool:
        """
        Проверить права доступа пользователя к документу
        
        Иерархия:
        1. Системный администратор
        2. Владелец документа
        3. Явные права в document_collaborators
        4. Публичный доступ (только для view)
        """
        cache_key = f"perm:{user_id}:{doc_id}:{required_permission}"
        cached_result = await cache.get_cached_permission(cache_key)
        if cached_result is not None:
            return cached_result
        
        async with self.pool.acquire() as conn:
            # 1. Проверка системного администратора
            user = await self.get_user_by_id(user_id)
            if user and user.get('role') == 'admin':
                await cache.set_cached_permission(cache_key, True)
                return True

            # 2. Получение информации о документе
            doc_row = await conn.fetchrow("""
                SELECT owner_id, is_public FROM documents WHERE id = $1
            """, doc_id)
            
            if not doc_row:
                await cache.set_cached_permission(cache_key, False)
                return False
            
            # 3. Проверка владельца
            if doc_row['owner_id'] == user_id:
                await cache.set_cached_permission(cache_key, True)
                return True

            # 4. Проверка явных прав
            perm_row = await conn.fetchrow("""
                SELECT permission_level 
                FROM document_collaborators 
                WHERE document_id = $1 AND user_id = $2
            """, doc_id, user_id)
            
            if perm_row:
                permission_level = perm_row['permission_level']
                has_permission = self._has_permission(permission_level, required_permission)
                await cache.set_cached_permission(cache_key, has_permission)
                return has_permission

            # 5. Проверка публичного доступа
            if required_permission == 'view' and doc_row['is_public']:
                await cache.set_cached_permission(cache_key, True)
                return True
            
            await cache.set_cached_permission(cache_key, False)
            return False
    
    def _has_permission(self, user_permission: str, required_permission: str) -> bool:
        """Проверка иерархии прав"""
        hierarchy = {'view': 1, 'comment': 2, 'edit': 3, 'admin': 4}
        user_level = hierarchy.get(user_permission, 0)
        required_level = hierarchy.get(required_permission, 0)
        return user_level >= required_level
    
    async def check_document_ownership(self, user_id: str, doc_id: str) -> bool:
        """Проверить, является ли пользователь владельцем документа"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT owner_id FROM documents WHERE id = $1
            """, doc_id)
            return row and row['owner_id'] == user_id
    
    async def check_system_admin(self, user_id: str) -> bool:
        """Проверить, является ли пользователь системным администратором"""
        user = await self.get_user_by_id(user_id)
        return user and user.get('role') == 'admin'
    
    # ===== МЕТОДЫ ДЛЯ ДОКУМЕНТОВ =====
    
    async def get_document(self, doc_id: str) -> Optional[Dict]:
        """Получить документ по ID"""
        cached = cache.get_document(doc_id)
        if cached:
            return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, title, content, owner_id, is_public, created_at, updated_at 
                FROM documents 
                WHERE id = $1
            """, doc_id)
            
            if row:
                document = dict(row)
                cache.set_document(doc_id, document)
                return document
            return None
    
    async def create_document(self, title: str, content: str, owner_id: str) -> Optional[Dict]:
        """Создать новый документ"""
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow("""
                    INSERT INTO documents (title, content, owner_id) 
                    VALUES ($1, $2, $3)
                    RETURNING id, title, content, owner_id, is_public, created_at, updated_at
                """, title, content, owner_id)
                
                if row:
                    document = dict(row)
                    return document
            except Exception as e:
                print(f"Error creating document: {e}")
                return None
    
    async def update_document(self, doc_id: str, title: str, content: str) -> Optional[Dict]:
        """Обновить документ"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE documents 
                SET title = $1, content = $2, updated_at = CURRENT_TIMESTAMP 
                WHERE id = $3 
                RETURNING id, title, content, owner_id, is_public, created_at, updated_at
            """, title, content, doc_id)
            
            if row:
                document = dict(row)
                cache.invalidate_document(doc_id)
                return document
            return None
    
    async def delete_document(self, doc_id: str) -> bool:
        """Удалить документ"""
        async with self.pool.acquire() as conn:
            try:
                result = await conn.execute("""
                    DELETE FROM documents WHERE id = $1
                """, doc_id)
                
                cache.invalidate_document(doc_id)
                await cache.invalidate_document_permissions(doc_id)
                return "DELETE 1" in result
            except Exception as e:
                print(f"Error deleting document: {e}")
                return False
    
    async def get_user_documents(self, user_id: str) -> List[Dict]:
        """Получить все документы, доступные пользователю"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT d.id, d.title, d.content, d.owner_id, 
                       d.is_public, d.created_at, d.updated_at,
                       CASE 
                           WHEN d.owner_id = $1 THEN 'owner'
                           WHEN dc.permission_level IS NOT NULL THEN dc.permission_level
                           WHEN d.is_public THEN 'public'
                           ELSE 'none'
                       END as access_level
                FROM documents d
                LEFT JOIN document_collaborators dc 
                    ON d.id = dc.document_id AND dc.user_id = $1
                WHERE d.owner_id = $1 
                   OR dc.user_id = $1 
                   OR d.is_public = TRUE
                ORDER BY d.updated_at DESC
            """, user_id)
            
            documents = [dict(row) for row in rows]
            
            for doc in documents:
                cache.set_document(doc['id'], doc)
            
            return documents
    
    async def get_document_collaborators(self, doc_id: str) -> List[Dict]:
        """Получить список всех пользователей с доступом к документу"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT u.id, u.username, u.email, dc.permission_level, dc.invited_at,
                       (d.owner_id = u.id) as is_owner
                FROM document_collaborators dc
                JOIN users u ON dc.user_id = u.id
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.document_id = $1
                ORDER BY 
                    CASE WHEN d.owner_id = u.id THEN 0 ELSE 1 END,
                    dc.permission_level DESC
            """, doc_id)
            
            return [dict(row) for row in rows]
    
    # ===== МЕТОДЫ ДЛЯ УПРАВЛЕНИЯ ПРАВАМИ =====
    
    async def set_document_permission(self, doc_id: str, user_id: str, permission: str) -> bool:
        """Установить права доступа к документу"""
        if permission not in ['view', 'comment', 'edit', 'admin']:
            return False
        
        async with self.pool.acquire() as conn:
            try:
                # Проверяем, не пытаемся ли изменить права владельца
                doc = await self.get_document(doc_id)
                if doc and doc['owner_id'] == user_id:
                    return False
                
                await conn.execute("""
                    INSERT INTO document_collaborators (document_id, user_id, permission_level)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (document_id, user_id) DO UPDATE
                    SET permission_level = $3
                """, doc_id, user_id, permission)

                await cache.invalidate_user_permissions(user_id, doc_id)
                cache.invalidate_document(doc_id)
                return True
            except Exception as e:
                print(f"Error setting document permission: {e}")
                return False
    
    async def remove_document_permission(self, doc_id: str, user_id: str) -> bool:
        """Удалить права доступа к документу"""
        async with self.pool.acquire() as conn:
            try:
                # Нельзя удалить права у владельца
                doc = await self.get_document(doc_id)
                if doc and doc['owner_id'] == user_id:
                    return False
                
                await conn.execute("""
                    DELETE FROM document_collaborators 
                    WHERE document_id = $1 AND user_id = $2
                """, doc_id, user_id)
                
                await cache.invalidate_user_permissions(user_id, doc_id)
                cache.invalidate_document(doc_id)
                return True
            except Exception as e:
                print(f"Error removing document permission: {e}")
                return False
    
    async def toggle_document_visibility(self, doc_id: str, user_id: str, is_public: bool) -> bool:
        """Сделать документ публичным/приватным"""
        async with self.pool.acquire() as conn:
            try:
                # Проверяем права
                has_access = await self.check_permission(user_id, doc_id, 'admin')
                if not has_access:
                    return False
                
                await conn.execute("""
                    UPDATE documents 
                    SET is_public = $1, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = $2
                """, is_public, doc_id)
                
                cache.invalidate_document(doc_id)
                await cache.invalidate_document_permissions(doc_id)
                return True
            except Exception as e:
                print(f"Error toggling document visibility: {e}")
                return False
    
    async def search_documents(self, query: str, user_id: str) -> List[Dict]:
        """Поиск документов по названию и содержимому"""
        async with self.pool.acquire() as conn:
            search_term = f"%{query}%"
            rows = await conn.fetch("""
                SELECT d.id, d.title, d.content, d.owner_id, d.is_public,
                       d.created_at, d.updated_at,
                       CASE 
                           WHEN d.owner_id = $2 THEN 'owner'
                           WHEN dc.permission_level IS NOT NULL THEN dc.permission_level
                           WHEN d.is_public THEN 'public'
                           ELSE 'none'
                       END as access_level
                FROM documents d
                LEFT JOIN document_collaborators dc 
                    ON d.id = dc.document_id AND dc.user_id = $2
                WHERE (d.title ILIKE $1 OR d.content ILIKE $1)
                  AND (d.owner_id = $2 
                       OR dc.user_id = $2 
                       OR d.is_public = TRUE)
                ORDER BY d.updated_at DESC
            """, search_term, user_id)
            
            return [dict(row) for row in rows]

db = Database()