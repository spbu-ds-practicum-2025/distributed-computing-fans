# Conspektor API Contracts

Этот документ описывает API:
- просмотр списка документов
- получение конкретного документа
- сохранение документа
- WebSocket для синхронного редактирования

---
# 1. Общая архитектура (MVP)

Все запросы выполняются к **API Gateway**.
Ни один клиент не обращается к внутренним сервисам напрямую.

Client → API Gateway → (REST) → Document Service → PostgreSQL

Document Service отвечает за хранение документов,  
Collaboration Hub — за синхронизацию изменений в реальном времени.


---
# 2. REST API (через API Gateway)

Все запросы отправляются на: http://localhost:8000

## 2.1. Получить список документов

### **GET /documents**

Получить список всех документов.

#### Пример запроса
```http
GET http://localhost:8000/documents
```

Ответ 200 OK:
```json
[
    {
        "id": 1,
        "title": "Demo document",
        "updated_at": "2025-11-19T12:00:00Z"
    }
]
```

## 2.2. Получить документ по ID

### **GET /documents/{id}**

Возвращает содержимое документа.

#### Пример запроса
```http
GET http://localhost:8000/documents/1
```

Ответ 200 OK:
```json
[
    {
    "id": 1,
    "title": "Demo document",
    "content": "Hello world!",
    "updated_at": "2025-11-19T12:00:00Z"
    }
]
```

Ошибка 404:
```json
[
    {
    "detail": "Document not found"
    }
]
```

## 2.3. Обновить документ целиком

### **PUT /documents/{id}**

Используется для сохранения текста в базу.

#### Пример запроса
```http
PUT http://localhost:8000/documents/1
Content-Type: application/json

{
  "title": "Demo document",
  "content": "New content here..."
}
```

Ответ 200 OK:
```json
[
    {
    "id": 1,
    "title": "Demo document",
    "content": "New content here...",
    "updated_at": "2025-11-19T12:00:05Z"
    }
]
```

Ошибка 400 (неверный формат):
```json
[
    {
    "detail": "Invalid request body"
    }
]
```

---
# 3. WebSocket API (через API Gateway)

WebSocket используется для редактирования документа в реальном времени.

#### Подключение:
```bash
ws://localhost:8000/ws/documents/{id}
```

#### Фронтенд-пример:
```js
const ws = new WebSocket("ws://localhost:8000/ws/documents/1");
```


## 3.1. Формат сообщений

#### Клиент → Сервер
Отправляет изменения документа.

Тип: change
```json
{
  "type": "change",
  "content": "полный текст документа"
}
```

В MVP мы не используем CRDT.
Фронтенд пересылает содержимое целиком.

#### Сервер → Клиент
Отправляет новое содержимое другим участникам.

Тип: update
```json
{
  "type": "update",
  "content": "обновлённый текст"
}
```

#### Первичное состояние
Отправляется сразу после подключения.

Тип: initial
```json
{
  "type": "initial",
  "content": "актуальный текст документа"
}
```


## 3.2. Ошибки (WS)

Например:
```json
{
  "type": "error",
  "message": "Document not found"
}
```


---
# 4. Поведение системы
1. Клиент подключается по WebSocket к документу.
2. Gateway проксирует запрос в Collaboration Hub (в будущем).
3. Collaboration Hub:
    получает текст документа из Document Service
    отправляет клиенту { type: "initial", content: ... }
4. Клиент редактирует текст и отправляет { type: "change" }.
5. Collaboration Hub:
    обновляет своё состояние
    рассылает всем другим клиентам { type: "update" }
6. Периодически Collaboration Hub отправляет текст в Document Service (по REST).


---
# 5. Стандартизированные ошибки

REST ошибки:

1. 400:
```json
{ "detail": "Bad request" }
```

2. 404:
```json
{ "detail": "Not found" }
```

3. 500:
```json
{ "detail": "Internal server error" }
```


---
# 6. Пример потоков данных

## 6.1. Открытие документа
Frontend → Gateway → GET /documents/1 → Document Service → DB

## 6.1. Редактирование
Frontend → WS change → Gateway → Collaboration Hub → другие клиенты

## 6.1. Сохранение в базу
Collaboration Hub → PUT /documents/1 → Document Service → PostgreSQL


---
# 7. Контакты сервисов (локально)

| Сервис            | Порт | Протокол |
| ----------------- | ---- | -------- |
| API Gateway       | 8000 | HTTP/WS  |
| Document Service  | 8001 | HTTP     |
| Collaboration Hub | 8002 | WS/HTTP  |
| PostgreSQL        | 5432 | DB       |


---
# 8. Статус документа
Должен обновляться при изменениях API