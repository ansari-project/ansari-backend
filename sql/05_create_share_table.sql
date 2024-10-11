CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE TABLE share (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT
);
