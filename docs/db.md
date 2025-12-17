# Conspektor Database Documentation

Этот документ описывает структуру базы данных и её взаимодействие с сервисами.

---
## 1. Общая архитектура базы данных

**PostgreSQL** является основной реляционной базой данных системы.
Все сервисы работают с одной БД, но через разные таблицы/схемы.

Document Service → PostgreSQL (документы, пользователи, права доступа)
Future Services  → PostgreSQL (разные модули)

---
## 2. Текущая схема базы данных

### 2.1. Таблица пользователей (`users`)
Хранит информацию о пользователях системы.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Поля:**
- `id` - уникальный идентификатор пользователя (UUID)
- `email` - электронная почта (уникальная)
- `username` - имя пользователя (уникальное)
- `created_at`, `updated_at` - метки времени

### 2.2. Таблица документов (`documents`)
Основная таблица для хранения документов.

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL DEFAULT 'Без названия',
    content TEXT NOT NULL DEFAULT '',
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Поля:**
- `id` - уникальный идентификатор документа (UUID)
- `title` - заголовок документа
- `content` - содержимое документа в текстовом формате
- `owner_id` - владелец документа (ссылка на users.id)
- `created_at`, `updated_at` - метки времени

### 2.3. Таблица совместного доступа (`document_collaborators`)
Управляет правами доступа к документам.

```sql
CREATE TABLE document_collaborators (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    permission_level VARCHAR(20) CHECK (permission_level IN ('view', 'comment', 'edit')),
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, user_id)
);
```

**Поля:**
- `document_id`, `user_id` - составной первичный ключ
- `permission_level` - уровень доступа: просмотр, комментирование, редактирование
- `invited_at` - время приглашения

### 2.4. Таблица версий документов (`document_versions`)
Хранит историю изменений для возможности отката.

```sql
CREATE TABLE document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.5. Таблица сессий редактирования (`editing_sessions`)
Отслеживает активные сессии редактирования.

```sql
CREATE TABLE editing_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    last_activity TIMESTAMPTZ DEFAULT NOW()
);
```

---
## 3. Индексы для производительности

```sql
-- Для быстрого поиска документов по владельцу
CREATE INDEX idx_documents_owner ON documents(owner_id);

-- Для сортировки документов по времени обновления
CREATE INDEX idx_documents_updated ON documents(updated_at DESC);

-- Для поиска документов пользователя
CREATE INDEX idx_collaborators_user ON document_collaborators(user_id);

-- Для быстрого доступа к версиям документа
CREATE INDEX idx_document_versions_doc_id ON document_versions(document_id);

-- Для сортировки версий по времени создания
CREATE INDEX idx_document_versions_created_at ON document_versions(created_at DESC);

-- Для управления активными сессиями
CREATE INDEX idx_editing_sessions_doc_user ON editing_sessions(document_id, user_id);
CREATE INDEX idx_editing_sessions_activity ON editing_sessions(last_activity);
```

---
## 4. Тестовые данные

Система включает начальные тестовые данные:

```sql
-- Тестовый пользователь
INSERT INTO users (id, email, username) VALUES 
    ('11111111-1111-1111-1111-111111111111', 'test@example.com', 'testuser')
ON CONFLICT (email) DO NOTHING;

-- Тестовый документ
INSERT INTO documents (id, title, content, owner_id) VALUES 
    ('22222222-2222-2222-2222-222222222222', 'Добро пожаловать!', 'Это тестовый документ', '11111111-1111-1111-1111-111111111111')
ON CONFLICT (id) DO NOTHING;
```

---
## 5. Взаимодействие сервисов с БД

### 5.1. Document Service
**Основные операции:**
- `GET /documents` → `SELECT * FROM documents ORDER BY updated_at DESC`
- `GET /documents/{id}` → `SELECT * FROM documents WHERE id = $1`
- `POST /documents` → `INSERT INTO documents (title, content) VALUES ($1, $2)`
- `PUT /documents/{id}` → `UPDATE documents SET title=$1, content=$2 WHERE id=$3`

**Используемые таблицы:**
- `documents` - основная работа с документами
- `users` - информация о владельцах
- `document_collaborators` - управление доступом

### 5.2. Подключение к БД
**Connection String:**
```
postgresql://app:password@postgres:5432/conspektor
```

**Переменные окружения:**
- `DATABASE_URL` - строка подключения
- `DB_NAME` - имя базы данных (по умолчанию: conspektor)
- `DB_USER` - пользователь (по умолчанию: app)
- `DB_PASSWORD` - пароль (по умолчанию: password)

---
## 6. Миграции и инициализация

### 6.1. Автоматическая инициализация
При первом запуске выполняется `init.sql` через:
```yaml
# docker-compose.yml
volumes:
  - ./services/database/init.sql:/docker-entrypoint-initdb.d/init.sql
```

### 6.2. Порядок создания объектов
1. Таблицы (`users`, `documents`, `document_collaborators`)
2. Дополнительные таблицы (`document_versions`, `editing_sessions`)
3. Индексы для производительности
4. Тестовые данные

---
## 7. Резервное копирование и восстановление

### 7.1. Ручное резервное копирование
```bash
docker-compose exec postgres pg_dump -U app -d conspektor -Fc > backup.dump
```

### 7.2. Восстановление из резервной копии
```bash
docker-compose exec postgres pg_restore -U app -d conspektor -c backup.dump
```

---
## 8. Мониторинг и обслуживание

### 8.1. Проверка состояния БД
```bash
# Проверка подключения
docker-compose exec postgres pg_isready -U app -d conspektor

# Проверка размера БД
docker-compose exec postgres psql -U app -d conspektor -c "SELECT pg_size_pretty(pg_database_size('conspektor'));"

# Активные подключения
docker-compose exec postgres psql -U app -d conspektor -c "SELECT count(*) FROM pg_stat_activity;"
```

### 8.2. Статистика использования
```sql
-- Количество документов
SELECT COUNT(*) as total_documents FROM documents;

-- Количество пользователей  
SELECT COUNT(*) as total_users FROM users;

-- Самые активные документы
SELECT title, updated_at FROM documents ORDER BY updated_at DESC LIMIT 5;
```

---
## 9. Планы развития

### 9.1. Ближайшие улучшения
- [ ] Кэширование часто запрашиваемых документов в Redis
- [ ] Репликация для чтения
- [ ] Автоматические бэкапы
- [ ] Мониторинг медленных запросов

### 9.2. Будущие расширения
- [ ] Full-text search для содержимого документов
- [ ] Шардирование по пользователям
- [ ] Архивация старых версий документов
- [ ] Расширенная система прав доступа

---
## 10. Контакты и порты

| Компонент       | Порт  | Назначение |
|-----------------|-------|------------|
| PostgreSQL      | 5432  | Основная БД |
| Redis           | 6379  | Кэширование |

**Локальное подключение:**
```bash
psql -h localhost -p 5432 -U app -d conspektor
```
