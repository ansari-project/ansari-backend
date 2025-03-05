-- NOTE: This is a temporary script that will be used for prod's DB, then deleted

-- Start a transaction to ensure atomicity
BEGIN;

-- Create the source_type enum with all four values matching schema
CREATE TYPE source_type AS ENUM ('ios', 'android', 'webpage', 'whatsapp');

-- Step 1: Modify the users table to include WhatsApp fields and use initial_source
ALTER TABLE users 
    ADD COLUMN initial_source source_type NOT NULL DEFAULT 'webpage',
    ADD COLUMN phone_num VARCHAR(20) UNIQUE;

-- Create index for phone number lookup
CREATE INDEX idx_users_phone_num ON users (phone_num) WHERE phone_num IS NOT NULL;

-- Step 2: Create a temporary mapping table to track WhatsApp user ID to new UUID mapping
CREATE TEMPORARY TABLE whatsapp_user_mapping AS
SELECT id AS old_id, uuid_generate_v4() AS new_uuid
FROM users_whatsapp;

-- Step 3: Migrate WhatsApp users to the main users table
INSERT INTO users (
    id, email, first_name, last_name, preferred_language, 
    is_guest, created_at, updated_at, initial_source, phone_num
)
SELECT 
    wum.new_uuid, NULL, uw.first_name, uw.last_name, uw.preferred_language,
    FALSE, uw.created_at, uw.updated_at, 'whatsapp', uw.phone_num
FROM users_whatsapp uw
JOIN whatsapp_user_mapping wum ON uw.id = wum.old_id
ON CONFLICT (phone_num) DO NOTHING;

-- Step 4: Modify threads table to include initial_source
ALTER TABLE threads ADD COLUMN initial_source source_type NOT NULL DEFAULT 'webpage';

-- Step 5: Migrate WhatsApp threads to main threads table
INSERT INTO threads (
    id, name, user_id, created_at, updated_at, initial_source
)
SELECT 
    tw.id, tw.name, 
    (SELECT u.id FROM users u WHERE u.phone_num = 
        (SELECT uw.phone_num FROM users_whatsapp uw WHERE uw.id = tw.user_id_whatsapp)
    ),
    tw.created_at, tw.updated_at, 'whatsapp'
FROM threads_whatsapp tw;

-- Step 6: Modify messages table to include initial_source
ALTER TABLE messages ADD COLUMN initial_source source_type NOT NULL DEFAULT 'webpage';

-- Step 7: Migrate WhatsApp messages to main messages table
INSERT INTO messages (
    user_id, thread_id, role, tool_name, tool_details, 
    ref_list, content, timestamp, created_at, updated_at, initial_source
)
SELECT 
    (SELECT u.id FROM users u WHERE u.phone_num = 
        (SELECT uw.phone_num FROM users_whatsapp uw WHERE uw.id = mw.user_id_whatsapp)
    ),
    mw.thread_id, mw.role, mw.tool_name, mw.tool_details,
    mw.ref_list, mw.content, mw.timestamp, mw.created_at, mw.updated_at, 'whatsapp'
FROM messages_whatsapp mw;

-- Step 8: Drop WhatsApp-specific tables after migration
DROP TABLE messages_whatsapp;
DROP TABLE threads_whatsapp;
DROP TABLE users_whatsapp;

-- Drop temporary tables
DROP TABLE whatsapp_user_mapping;

-- Commit all changes if everything succeeded
COMMIT;

-- In case of any failure, all changes will be rolled back
-- ROLLBACK; -- Uncomment this line if executing manually and an error occurs