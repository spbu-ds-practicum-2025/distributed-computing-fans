"""
Простой HTTP Message Broker.
Хранит события в памяти и отдаёт через long polling.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import asyncio
import uvicorn
from datetime import datetime
import json

app = FastAPI(title="Simple Message Broker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище событий в памяти
events = []
event_lock = asyncio.Lock()
subscribers = []

class Event(BaseModel):
    document_id: str
    event_type: str = "document_update"
    content: str = ""
    user_id: str = None
    timestamp: str = None

@app.post("/events")
async def publish_event(event: Event):
    """Принять событие от Collaboration Hub"""
    if event.timestamp is None:
        event.timestamp = datetime.utcnow().isoformat()
    
    async with event_lock:
        events.append(event.dict())
        
        # Уведомляем всех подписчиков
        for queue in subscribers:
            await queue.put(event.dict())
    
    print(f"[Broker] Event published for doc {event.document_id}")
    return {"status": "ok", "event_id": len(events)}

@app.get("/events")
async def get_events(client_id: str, last_event_id: int = -1):
    """Long polling для получения событий"""
    # Проверяем, есть ли новые события
    async with event_lock:
        if last_event_id < len(events) - 1:
            new_events = events[last_event_id + 1:]
            return {
                "client_id": client_id,
                "last_event_id": len(events) - 1,
                "events": new_events
            }
    
    # Нет новых событий - подписываемся и ждём
    queue = asyncio.Queue()
    subscribers.append(queue)
    
    try:
        # Ждём новое событие 30 секунд
        event = await asyncio.wait_for(queue.get(), timeout=30.0)
        subscribers.remove(queue)
        
        return {
            "client_id": client_id,
            "last_event_id": len(events) - 1,
            "events": [event]
        }
    except asyncio.TimeoutError:
        subscribers.remove(queue)
        return {
            "client_id": client_id,
            "last_event_id": last_event_id,
            "events": []
        }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "events_count": len(events),
        "subscribers": len(subscribers)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)