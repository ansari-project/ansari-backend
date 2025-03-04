-- Side note (tip): While developing locally, if you use a tool like DBeaver, and encounter a scope-related error, 
-- you can append each table name with `public.` to fix the error, as `public` is the default schema name in PostgreSQL.

-- Extensions (from 05_create_share_table.sql)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Type definitions (from 04_create_feedback_table.sql)
CREATE TYPE feedback_class AS ENUM ('thumbsup', 'thumbsdown', 'redflag');

-- Core tables
-- Users table (from 01_create_tables.sql, with UUID from 12_alter_user_id_to_uuid.sql)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(100) UNIQUE, -- Can be null if it is a guest account
    password_hash VARCHAR(255), -- Can be null if it is a guest account
    first_name VARCHAR(50), -- Can be null if it is a guest account
    last_name VARCHAR(50), -- Can be null if it is a guest account
    preferred_language VARCHAR(10) DEFAULT 'en',
    is_guest BOOLEAN NOT NULL DEFAULT FALSE, 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- WhatsApp users table (from 10_create_whatsapp_tables.sql, with UUID user_id from 12_alter_user_id_to_uuid.sql)
CREATE TABLE users_whatsapp (
    id SERIAL PRIMARY KEY,
    user_id UUID, -- Left here in case we want to get whatsapp context into Ansari's main website
    phone_num VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(50), -- Can be null if user didn't specify
    last_name VARCHAR(50), -- Can be null if user didn't specify
    preferred_language VARCHAR(10) DEFAULT 'en', -- Could be programmatically deduced
    loc_lat FLOAT, -- Can be null if user didn't specify
    loc_long FLOAT, -- Can be null if user didn't specify
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Index on WhatsApp users (from 10_create_whatsapp_tables.sql)
CREATE INDEX idx_users_whatsapp_phone_num ON users_whatsapp (phone_num);

-- Preferences table (from 01_create_tables.sql, with UUID user_id from 12_alter_user_id_to_uuid.sql)
CREATE TABLE preferences (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    pref_key VARCHAR(100) NOT NULL,
    pref_value VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unique (user_id, pref_key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Thread tables
-- Threads table (from 01_create_tables.sql, with UUID from 08_alter_chat_id_to_uuid.sql and UUID user_id from 12_alter_user_id_to_uuid.sql)
CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100),
    user_id UUID NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- WhatsApp threads table (from 10_create_whatsapp_tables.sql)
CREATE TABLE threads_whatsapp (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id_whatsapp INTEGER NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id_whatsapp) REFERENCES users_whatsapp(id)
);

-- WhatsApp threads index (from 10_create_whatsapp_tables.sql)
CREATE INDEX idx_threads_whatsapp_updated_at ON threads_whatsapp (updated_at);

-- Authentication and tokens
-- Access tokens table (from 02_create_user_tokens.sql, renamed in 06_alter_user_tokens.sql, with UUID user_id from 12_alter_user_id_to_uuid.sql)
CREATE TABLE access_tokens (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    token VARCHAR(255) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Refresh tokens table (from 07_create_refresh_tokens.sql, with UUID user_id from 12_alter_user_id_to_uuid.sql)
CREATE TABLE refresh_tokens (
    id SERIAL PRIMARY KEY,
    access_token_id INTEGER NOT NULL,
    user_id UUID NOT NULL,
    token VARCHAR(255) NOT NULL, 
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (access_token_id) REFERENCES access_tokens(id) ON DELETE CASCADE
);

-- Reset tokens table (from 03_create_reset_tokens.sql, with UUID user_id from 12_alter_user_id_to_uuid.sql)
CREATE TABLE reset_tokens (
    user_id UUID PRIMARY KEY,
    token VARCHAR(255) NOT NULL, 
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Content tables
-- Messages table (from 01_create_tables.sql, with UUID thread_id from 08_alter_chat_id_to_uuid.sql, 
-- tool fields from 11_alter_tool_logic.sql, UUID user_id from 12_alter_user_id_to_uuid.sql, 
-- and ref_list from 13_add_ref_list_column.sql)
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    thread_id UUID NOT NULL,
    role TEXT NOT NULL, 
    tool_name TEXT,
    tool_details JSONB DEFAULT '{}'::jsonb,
    ref_list JSONB, -- Added from 13_add_ref_list_column.sql
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
);

-- Add comment to explain the ref_list column (from 13_add_ref_list_column.sql)
COMMENT ON COLUMN messages.ref_list IS 'JSON array containing reference list data for tool responses';

-- WhatsApp messages table (from 10_create_whatsapp_tables.sql with tool fields from 11_alter_tool_logic.sql
-- and ref_list from 13_add_ref_list_column.sql)
CREATE TABLE messages_whatsapp (
    id SERIAL PRIMARY KEY,
    user_id_whatsapp INTEGER NOT NULL,
    thread_id UUID NOT NULL,
    role TEXT NOT NULL, 
    tool_name TEXT,
    tool_details JSONB DEFAULT '{}'::jsonb,
    ref_list JSONB, -- Added from 13_add_ref_list_column.sql
    content TEXT NOT NULL, 
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id_whatsapp) REFERENCES users_whatsapp(id),
    FOREIGN KEY (thread_id) REFERENCES threads_whatsapp(id)
);

-- Add comment to explain the ref_list column (from 13_add_ref_list_column.sql)
COMMENT ON COLUMN messages_whatsapp.ref_list IS 'JSON array containing reference list data for tool responses';

-- Feedback table (from 04_create_feedback_table.sql, with UUID thread_id from 08_alter_chat_id_to_uuid.sql
-- and UUID user_id from 12_alter_user_id_to_uuid.sql)
CREATE TABLE feedback (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    thread_id UUID NOT NULL,
    message_id INTEGER NOT NULL,
    class feedback_class NOT NULL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id), 
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

-- Share table (from 05_create_share_table.sql)
CREATE TABLE share (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT
);

-- Quran review tables (from 09_create_quran_answer_tables.sql)
CREATE TABLE reviewers ( 
    id SERIAL PRIMARY KEY, 
    name VARCHAR(255) NOT NULL 
);

CREATE TABLE quran_answers (
    id SERIAL PRIMARY KEY, 
    surah INT, 
    ayah INT, 
    question TEXT, 
    ansari_answer TEXT, 
    review_result VARCHAR(20) CHECK (review_result IN ('pending', 'approved', 'edited', 'disapproved')),
    reviewed_by INT, 
    reviewer_comment TEXT,
    final_answer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reviewed_by) REFERENCES reviewers(id)
);
