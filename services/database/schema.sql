-- ===== 1. УДАЛЕНИЕ СУЩЕСТВУЮЩИХ ОБЪЕКТОВ =====
DROP TRIGGER IF EXISTS trigger_add_owner_as_admin ON documents CASCADE;
DROP TRIGGER IF EXISTS update_users_updated_at ON users CASCADE;
DROP TRIGGER IF EXISTS update_documents_updated_at ON documents CASCADE;

DROP FUNCTION IF EXISTS add_owner_as_admin CASCADE;
DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;

DROP TABLE IF EXISTS document_collaborators CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS users CASCADE;

DROP TYPE IF EXISTS permission_level CASCADE;
DROP TYPE IF EXISTS user_role CASCADE;

-- ===== 2. СОЗДАНИЕ ТИПОВ =====
CREATE TYPE user_role AS ENUM ('admin', 'user');
CREATE TYPE permission_level AS ENUM ('view', 'comment', 'edit', 'admin');

-- ===== 3. СОЗДАНИЕ ТАБЛИЦ =====
-- Пользователи
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    role user_role DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE users IS 'Таблица пользователей системы';

-- Документы
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL DEFAULT 'Без названия',
    content TEXT NOT NULL DEFAULT '',
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE documents IS 'Таблица документов';

-- Права доступа к документам (основная таблица для совместной работы)
CREATE TABLE document_collaborators (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    permission_level permission_level NOT NULL DEFAULT 'view',
    invited_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, user_id)
);

COMMENT ON TABLE document_collaborators IS 'Права доступа пользователей к документам';

-- ===== 4. ИНДЕКСЫ =====
-- Для пользователей
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);

-- Для документов
CREATE INDEX idx_documents_owner ON documents(owner_id);
CREATE INDEX idx_documents_public ON documents(is_public) WHERE is_public = TRUE;
CREATE INDEX idx_documents_updated ON documents(updated_at DESC);

-- Для прав доступа
CREATE INDEX idx_collaborators_user ON document_collaborators(user_id);
CREATE INDEX idx_collaborators_document ON document_collaborators(document_id);
CREATE INDEX idx_collaborators_user_document ON document_collaborators(user_id, document_id);

-- ===== 5. ТРИГГЕРЫ =====
-- Автоматическое добавление владельца как администратора
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

CREATE TRIGGER trigger_add_owner_as_admin
AFTER INSERT ON documents
FOR EACH ROW
EXECUTE FUNCTION add_owner_as_admin();

-- Автоматическое обновление updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ===== 6. ОСНОВНЫЕ ВЬЮХИ =====
-- Документы с информацией о владельце
CREATE OR REPLACE VIEW document_details AS
SELECT 
    d.*,
    u.username as owner_username,
    u.email as owner_email
FROM documents d
LEFT JOIN users u ON d.owner_id = u.id;

-- Права пользователя на документы (оптимизированная версия)
CREATE OR REPLACE VIEW user_document_access AS
SELECT 
    u.id as user_id,
    d.id as document_id,
    d.title,
    CASE 
        WHEN d.owner_id = u.id THEN 'admin'::permission_level
        WHEN dc.permission_level IS NOT NULL THEN dc.permission_level
        WHEN d.is_public THEN 'view'::permission_level
        ELSE NULL
    END as effective_permission,
    d.is_public,
    (d.owner_id = u.id) as is_owner
FROM users u
JOIN documents d ON 1=1
LEFT JOIN document_collaborators dc ON d.id = dc.document_id AND u.id = dc.user_id
WHERE d.owner_id = u.id 
   OR dc.user_id = u.id 
   OR d.is_public = TRUE;