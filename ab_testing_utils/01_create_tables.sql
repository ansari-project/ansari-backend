CREATE TABLE experiments (
    experiment_id SERIAL PRIMARY KEY,
    experiment_name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE models (
    model_id SERIAL PRIMARY KEY,
    model_name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    experiment_id INTEGER REFERENCES experiments(experiment_id)
);

CREATE TABLE conversations (
    conversation_id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models(model_id),
    conversation JSONB,
    timestamp TIMESTAMP WITH TIME ZONE
);

CREATE TABLE comparisons (
    comparison_id SERIAL PRIMARY KEY,
    model_a_id INTEGER REFERENCES models(model_id),
    model_b_id INTEGER REFERENCES models(model_id),
    conversation_a_id INTEGER REFERENCES conversations(conversation_id),
    conversation_b_id INTEGER REFERENCES conversations(conversation_id),
    user_vote VARCHAR(10) CHECK (user_vote IN ('A', 'B', 'Tie', 'Both Bad')),
    timestamp TIMESTAMP WITH TIME ZONE
);
