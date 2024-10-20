CREATE TABLE refresh_tokens (
    id SERIAL PRIMARY KEY,
    access_token_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    token VARCHAR(255) NOT NULL, 
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (access_token_id) REFERENCES access_tokens(id) ON DELETE CASCADE
); 