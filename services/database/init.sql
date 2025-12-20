-- ===== 1. ОСНОВНАЯ СХЕМА =====
-- Типы
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('admin', 'user');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'permission_level') THEN
        CREATE TYPE permission_level AS ENUM ('view', 'comment', 'edit', 'admin');
    END IF;
END $$;

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    role user_role DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица документов
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL DEFAULT 'Без названия',
    content TEXT NOT NULL DEFAULT '',
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица совместного доступа
CREATE TABLE IF NOT EXISTS document_collaborators (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    permission_level permission_level DEFAULT 'view',
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, user_id)
);

-- Таблица истории версий
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

-- Таблица системных ролей
CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role user_role DEFAULT 'user',
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    granted_by UUID REFERENCES users(id),
    PRIMARY KEY (user_id)
);

-- ===== 2. ИНДЕКСЫ =====
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);
CREATE INDEX IF NOT EXISTS idx_documents_public ON documents(is_public) WHERE is_public = TRUE;
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_collaborators_user ON document_collaborators(user_id);
CREATE INDEX IF NOT EXISTS idx_collaborators_doc ON document_collaborators(document_id);
CREATE INDEX IF NOT EXISTS idx_collaborators_doc_user_permission ON document_collaborators(document_id, user_id, permission_level);

CREATE INDEX IF NOT EXISTS idx_document_versions_doc_id ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_created_at ON document_versions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_editing_sessions_doc_user ON editing_sessions(document_id, user_id);
CREATE INDEX IF NOT EXISTS idx_editing_sessions_activity ON editing_sessions(last_activity);

-- ===== 3. ТРИГГЕРЫ =====
-- Функция и триггер для автоматического добавления владельца как администратора
CREATE OR REPLACE FUNCTION add_owner_as_admin()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO document_collaborators (document_id, user_id, permission_level)
    VALUES (NEW.id, NEW.owner_id, 'admin')
    ON CONFLICT (document_id, user_id) DO UPDATE
    SET permission_level = 'admin';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_add_owner_as_admin ON documents;
CREATE TRIGGER trigger_add_owner_as_admin
AFTER INSERT ON documents
FOR EACH ROW
EXECUTE FUNCTION add_owner_as_admin();

-- Функция и триггеры для обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();





-- Очищаем старые тестовые данные (если есть)
DELETE FROM editing_sessions;
DELETE FROM document_versions;
DELETE FROM document_collaborators;
DELETE FROM user_roles;
DELETE FROM documents;
DELETE FROM users;

-- Вставка тестовых пользователей
INSERT INTO users (id, email, username, role) VALUES 
    ('11111111-1111-1111-1111-111111111111', 'test1@example.com', 'testuser1', 'user'),
    ('22222222-2222-2222-2222-222222222222', 'test2@example.com', 'testuser2', 'user'),
    ('33333333-3333-3333-3333-333333333333', 'test3@example.com', 'testuser3', 'user'),
    ('44444444-4444-4444-4444-444444444444', 'admin@example.com', 'adminuser', 'admin')
ON CONFLICT (email) DO UPDATE 
SET username = EXCLUDED.username, role = EXCLUDED.role;

-- Вставка тестовых документов
INSERT INTO documents (id, title, content, owner_id, is_public) VALUES 
    ('11111111-1111-1111-1111-111111111110', 'Публичный документ 1', 'Это публичный тестовый документ. Доступен всем на чтение.', '11111111-1111-1111-1111-111111111111', TRUE),
    ('22222222-2222-2222-2222-222222222220', 'Приватный документ 2', 'Это приватный тестовый документ. Доступен только владельцу и приглашенным.', '22222222-2222-2222-2222-222222222222', FALSE),
    ('33333333-3333-3333-3333-333333333330', 'Публичный документ 3', 'Еще один публичный документ для тестирования.', '33333333-3333-3333-3333-333333333333', TRUE),
    ('44444444-4444-4444-4444-444444444440', 'Документ администратора', 'Документ, созданный системным администратором.', '44444444-4444-4444-4444-444444444444', FALSE)
ON CONFLICT (id) DO UPDATE 
SET title = EXCLUDED.title, content = EXCLUDED.content, owner_id = EXCLUDED.owner_id, is_public = EXCLUDED.is_public;

-- Назначение прав для тестирования
-- Пользователь 2 имеет права на редактирование документа 1
INSERT INTO document_collaborators (document_id, user_id, permission_level) VALUES 
    ('11111111-1111-1111-1111-111111111110', '22222222-2222-2222-2222-222222222222', 'edit'),
    ('22222222-2222-2222-2222-222222222220', '33333333-3333-3333-3333-333333333333', 'view'),
    ('33333333-3333-3333-3333-333333333330', '44444444-4444-4444-4444-444444444444', 'admin')
ON CONFLICT (document_id, user_id) DO UPDATE 
SET permission_level = EXCLUDED.permission_level;

-- История ролей
INSERT INTO user_roles (user_id, role, granted_by) VALUES 
    ('44444444-4444-4444-4444-444444444444', 'admin', '44444444-4444-4444-4444-444444444444')
ON CONFLICT (user_id) DO UPDATE 
SET role = EXCLUDED.role;
