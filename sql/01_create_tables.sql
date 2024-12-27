-- Side note (tip): If you use a tool like DBeaver, and encounter a scope-related error, 
-- you can append each table name with `public.` to fix the error, as `public` is the default schema name in PostgreSQL.

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) UNIQUE, -- Can be null if it is a guest account
    password_hash VARCHAR(255), -- Can be null if it is a guest account
    first_name VARCHAR(50), -- Can be null if it is a guest account
    last_name VARCHAR(50), -- Can be null if it is a guest account
    preferred_language VARCHAR(10) DEFAULT 'en',
    is_guest BOOLEAN NOT NULL DEFAULT FALSE, 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    pref_key VARCHAR(100) NOT NULL,
    pref_value VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unique (user_id, pref_key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE threads (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    thread_id INTEGER NOT NULL,
    role TEXT NOT NULL, 
    -- #TODO (odyash): check if "function" can be renamed to "tool" like the rest of the codebase or not
    function_name TEXT, 
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (thread_id) REFERENCES threads(id)
);
