CREATE TYPE feedback_class AS ENUM ('thumbsup', 'thumbsdown', 'redflag');

CREATE TABLE feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    thread_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    class feedback_class NOT NULL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id), 
    FOREIGN KEY (thread_id) REFERENCES threads(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);