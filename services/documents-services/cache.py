import redis.asyncio as redis
import json
import os

class Cache:
    def __init__(self):
        self.client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

    async def get_document(self, doc_id: str):
        data = await self.client.get(f"doc:{doc_id}")
        return json.loads(data) if data else None

    async def set_document(self, doc_id: str, document: dict):
        await self.client.set(f"doc:{doc_id}", json.dumps(document))

    async def invalidate_document(self, doc_id: str):
        await self.client.delete(f"doc:{doc_id}")

cache = Cache()
