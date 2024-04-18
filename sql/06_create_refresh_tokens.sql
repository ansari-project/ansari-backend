CREATE TABLE refresh_tokens (
    user_id INTEGER PRIMARY KEY,
    token VARCHAR(255) NOT NULL, 
    FOREIGN KEY (user_id) REFERENCES users(id)
); 