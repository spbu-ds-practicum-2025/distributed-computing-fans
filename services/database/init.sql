-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Создание таблицы документов
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL DEFAULT 'Без названия',
    content TEXT NOT NULL DEFAULT '',
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица для совместного доступа
CREATE TABLE IF NOT EXISTS document_collaborators (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    permission_level VARCHAR(20) CHECK (permission_level IN ('view', 'comment', 'edit')),
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, user_id)
);

-- Таблица для хранения истории изменений документов (для откатов и аудита)
CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица сессий редактирования
CREATE TABLE IF NOT EXISTS editing_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    last_activity TIMESTAMPTZ DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_document_versions_doc_id ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_created_at ON document_versions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_editing_sessions_doc_user ON editing_sessions(document_id, user_id);
CREATE INDEX IF NOT EXISTS idx_editing_sessions_activity ON editing_sessions(last_activity);

-- Тестовые данные
INSERT INTO users (id, email, username) VALUES 
    ('11111111-1111-1111-1111-111111111111', 'test@example.com', 'testuser')
ON CONFLICT (email) DO NOTHING;

INSERT INTO documents (id, title, content, owner_id) VALUES 
    ('22222222-2222-2222-2222-222222222222', 'Добро пожаловать!', 'Это тестовый документ', '11111111-1111-1111-1111-111111111111')
ON CONFLICT (id) DO NOTHING;