CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users_whatsapp (
    id SERIAL PRIMARY KEY,
    user_id INTEGER, -- Left here in case we want to get whatsapp context into Ansari's main website (possible #TODO(odyash) in the far future)
    phone_num VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(50), -- Can be null if user didn't specify (#TODO(odyash))
    last_name VARCHAR(50), -- Can be null if user didn't specify (#TODO(odyash))
    preferred_language VARCHAR(10) DEFAULT 'en', -- Could be programmatically deduced using initial message's language, country code, other table fields (#TODO(odyash))
    loc_lat FLOAT, -- Can be null if user didn't specify (#TODO(odyash))
    loc_long FLOAT, -- Can be null if user didn't specify (#TODO(odyash))
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Create an index on the phone_num column to improve search performance,
-- since a fair amount of queries will be based on phone_num
CREATE INDEX idx_users_whatsapp_phone_num ON users_whatsapp (phone_num);

CREATE TABLE threads_whatsapp (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id_whatsapp INTEGER NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id_whatsapp) REFERENCES users_whatsapp(id)
);

-- Create an index on the updated_at column to improve sorting performance
CREATE INDEX idx_threads_whatsapp_updated_at ON threads_whatsapp (updated_at);

CREATE TABLE messages_whatsapp (
    id SERIAL PRIMARY KEY,
    user_id_whatsapp INTEGER NOT NULL,
    thread_id UUID NOT NULL,
    role TEXT NOT NULL, 
    function_name TEXT, -- #TODO(odyash): check if "function" can be renamed to "tool" like the rest of the codebase or not
    content TEXT NOT NULL, 
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Not sure if this useful, as we have timestamp
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Same thing here
    FOREIGN KEY (user_id_whatsapp) REFERENCES users_whatsapp(id),
    FOREIGN KEY (thread_id) REFERENCES threads_whatsapp(id)
);

-- Debugging notes: run below commands to untie dependencies and drop tables 
-- (if you're still prototyping with the tables' final schema)

-- -- Drop foreign key constraints
-- ALTER TABLE users_whatsapp DROP CONSTRAINT users_whatsapp_user_id_fkey;
-- ALTER TABLE messages_whatsapp DROP CONSTRAINT messages_whatsapp_user_id_whatsapp_fkey;

-- -- Drop the tables
-- DROP TABLE IF EXISTS users_whatsapp;
-- DROP TABLE IF EXISTS messages_whatsapp;
-- DROP TABLE IF EXISTS threads_whatsapp;