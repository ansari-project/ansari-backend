-- Start a transaction to ensure atomicity
BEGIN;

-- Enable the UUID extension to allow generation of UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Add a new UUID column to the 'threads' table, set it as non-nullable, and add a default value for UUID generation
ALTER TABLE threads ADD COLUMN new_id UUID DEFAULT uuid_generate_v4() NOT NULL;

-- Populate 'new_id' with unique UUIDs for existing rows
UPDATE threads SET new_id = uuid_generate_v4();

-- Add new UUID columns to 'messages' and 'feedback' tables, set them as non-nullable
ALTER TABLE messages ADD COLUMN new_thread_id UUID NOT NULL;
ALTER TABLE feedback ADD COLUMN new_thread_id UUID NOT NULL;

-- Update 'messages' with the new UUID thread IDs
UPDATE messages m
SET new_thread_id = t.new_id
FROM threads t
WHERE m.thread_id = t.id;

-- Update 'feedback' with the new UUID thread IDs
UPDATE feedback f
SET new_thread_id = t.new_id
FROM threads t
WHERE f.thread_id = t.id;

-- Drop existing foreign key constraints on 'thread_id' to prepare for column changes
ALTER TABLE messages DROP CONSTRAINT messages_thread_id_fkey;
ALTER TABLE feedback DROP CONSTRAINT feedback_thread_id_fkey;

-- Remove the old 'thread_id' columns from 'messages' and 'feedback'
ALTER TABLE messages DROP COLUMN thread_id;
ALTER TABLE feedback DROP COLUMN thread_id;

-- Rename 'new_thread_id' to 'thread_id' in both tables
ALTER TABLE messages RENAME COLUMN new_thread_id TO thread_id;
ALTER TABLE feedback RENAME COLUMN new_thread_id TO thread_id;

-- Drop the old primary key constraint on 'threads'
ALTER TABLE threads DROP CONSTRAINT threads_pkey;

-- Remove the old 'id' column from 'threads'
ALTER TABLE threads DROP COLUMN id;

-- Rename 'new_id' to 'id' in 'threads'
ALTER TABLE threads RENAME COLUMN new_id TO id;

-- Set the new 'id' column as the primary key in 'threads'
ALTER TABLE threads ADD PRIMARY KEY (id);

-- Set the default value of 'id' to generate a new UUID automatically for new records
ALTER TABLE threads ALTER COLUMN id SET DEFAULT uuid_generate_v4();

-- Recreate foreign key constraints referencing the updated 'threads(id)' with proper ON DELETE actions
ALTER TABLE messages
ADD CONSTRAINT messages_thread_id_fkey
FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE;

ALTER TABLE feedback
ADD CONSTRAINT feedback_thread_id_fkey
FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE;

-- Commit the transaction if all operations succeed
COMMIT;

-- In case of any failure, all changes will be rolled back
-- ROLLBACK; -- Uncomment this line if executing manually and an error occurs