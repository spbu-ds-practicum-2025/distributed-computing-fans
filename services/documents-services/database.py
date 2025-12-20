import asyncpg
import os
from typing import List, Optional, Dict, Any
import json
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
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Получить пользователя по username"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, email, username, created_at
                FROM users 
                WHERE username = $1
            """, username)
            return dict(row) if row else None

    async def get_documents(self) -> List[Dict]:
        """Получить список всех документов"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, title, content, created_at, updated_at 
                FROM documents 
                ORDER BY updated_at DESC
            """)
            return [dict(row) for row in rows]
        
    async def get_user_documents(self, user_id: str) -> List[Dict]:
        """Получить документы пользователя по owner_id"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, title, content, owner_id, created_at, updated_at 
                FROM documents 
                WHERE owner_id = $1
                ORDER BY updated_at DESC
            """, user_id)
            return [dict(row) for row in rows]
        
    async def get_document(self, doc_id: str) -> Optional[Dict]:
        # cached = await cache.get_document(doc_id)
        # if cached:
        #     return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, title, content, created_at, updated_at 
                FROM documents 
                WHERE id = $1
            """, doc_id)
            
            if row:
                document = dict(row)
                # await cache.set_document(doc_id, document)
                return document
            return None

    async def create_document(self, title: str, content: str, owner_id: str) -> Dict:
        """Создать новый документ"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO documents (title, content, owner_id) 
                VALUES ($1, $2, $3) 
                RETURNING id, title, content, created_at, updated_at
            """, title, content, owner_id)
            return dict(row)

    async def update_document(self, doc_id: str, content: str) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE documents 
                SET content = $1, updated_at = CURRENT_TIMESTAMP 
                WHERE id = $2 
                RETURNING id, title, content, created_at, updated_at
            """, content, doc_id)
            
            if row:
                document = dict(row)
                return document
            return None

    async def delete_document(self, doc_id: str) -> bool:
        """Удалить документ"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM documents WHERE id = $1
            """, doc_id)
            return "DELETE 1" in result

    async def create_user(self, email: str, username: str) -> Dict:
        """Создать пользователя"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO users (email, username) 
                VALUES ($1, $2) 
                RETURNING id, email, username, created_at
            """, email, username)
            return dict(row)

    async def add_collaborator(self, doc_id: str, user_id: str, permission: str = 'edit') -> bool:
        """Добавить collaborator к документу"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO document_collaborators (document_id, user_id, permission_level) 
                    VALUES ($1, $2, $3)
                """, doc_id, user_id, permission)
                return True
            except asyncpg.UniqueViolationError:
                return False

db = Database()