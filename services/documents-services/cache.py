import redis.asyncio as redis
import json
import os
from typing import Optional, Dict, Any

class Cache:
    def __init__(self):
        self.redis_client = redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
            encoding="utf-8"
        )
        self.document_cache = {}
    
    # ===== Redis методы для пользователей =====
    
    async def get_user(self, user_id: str) -> Optional[Dict]:
        try:
            data = await self.redis_client.get(f"user:{user_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"Redis error (get_user): {e}")
        return None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        try:
            user_id = await self.redis_client.get(f"username_lookup:{username}")
            if user_id:
                return await self.get_user(user_id)
        except Exception as e:
            print(f"Redis error (get_user_by_username): {e}")
        return None
    
    async def set_user(self, user_id: str, user_data: Dict) -> None:
        try:
            await self.redis_client.setex(
                f"user:{user_id}",
                3600,
                json.dumps(user_data)
            )
            if 'username' in user_data:
                await self.redis_client.setex(
                    f"username_lookup:{user_data['username']}",
                    3600,
                    user_id
                )
        except Exception as e:
            print(f"Redis error (set_user): {e}")
    
    async def invalidate_user(self, user_id: str) -> None:
        try:
            user = await self.get_user(user_id)
            if user and 'username' in user:
                await self.redis_client.delete(f"username_lookup:{user['username']}")
            await self.redis_client.delete(f"user:{user_id}")
        except Exception as e:
            print(f"Redis error (invalidate_user): {e}")
    
    # ===== In-memory методы для документов =====
    
    def get_document(self, doc_id: str) -> Optional[Dict]:
        return self.document_cache.get(doc_id)
    
    def set_document(self, doc_id: str, document: Dict) -> None:
        if len(self.document_cache) > 1000:
            oldest_key = next(iter(self.document_cache))
            self.document_cache.pop(oldest_key)
        self.document_cache[doc_id] = document
    
    def invalidate_document(self, doc_id: str) -> None:
        self.document_cache.pop(doc_id, None)
    
    def clear_document_cache(self) -> None:
        self.document_cache.clear()
    
    # ===== Методы для кэширования проверок прав =====
    
    async def get_cached_permission(self, cache_key: str) -> Optional[bool]:
        """Получить закэшированный результат проверки прав"""
        try:
            data = await self.redis_client.get(cache_key)
            if data is not None:
                return data == "true"
        except Exception as e:
            print(f"Redis error (get_cached_permission): {e}")
        return None
    
    async def set_cached_permission(self, cache_key: str, has_permission: bool) -> None:
        """Закэшировать результат проверки прав"""
        try:
            await self.redis_client.setex(
                cache_key,
                300,  # 5 минут TTL для проверок прав
                "true" if has_permission else "false"
            )
        except Exception as e:
            print(f"Redis error (set_cached_permission): {e}")
    
    async def get_user_permissions(self, user_id: str, doc_id: str) -> Optional[Dict]:
        try:
            data = await self.redis_client.get(f"permissions:{user_id}:{doc_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"Redis error (get_user_permissions): {e}")
        return None
    
    async def set_user_permissions(self, user_id: str, doc_id: str, permissions: Dict) -> None:
        try:
            await self.redis_client.setex(
                f"permissions:{user_id}:{doc_id}",
                1800,
                json.dumps(permissions)
            )
        except Exception as e:
            print(f"Redis error (set_user_permissions): {e}")
    
    async def invalidate_user_permissions(self, user_id: str, doc_id: str = None) -> None:
        try:
            if doc_id:
                await self.redis_client.delete(f"permissions:{user_id}:{doc_id}")
                pattern = f"permissions:{user_id}:{doc_id}:*"
                keys = await self.redis_client.keys(pattern)
                if keys:
                    await self.redis_client.delete(*keys)
            else:
                keys = await self.redis_client.keys(f"permissions:{user_id}:*")
                if keys:
                    await self.redis_client.delete(*keys)
        except Exception as e:
            print(f"Redis error (invalidate_user_permissions): {e}")
    
    async def invalidate_document_permissions(self, doc_id: str) -> None:
        """Инвалидировать все кэшированные права для документа"""
        try:
            pattern = f"permissions:*:{doc_id}*"
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
        except Exception as e:
            print(f"Redis error (invalidate_document_permissions): {e}")
    
    async def health_check(self) -> bool:
        try:
            await self.redis_client.ping()
            return True
        except:
            return False

cache = Cache()