-- Rename function_name column to tool_name in messages / messages_whatsapp tables
ALTER TABLE messages 
RENAME COLUMN function_name TO tool_name;

ALTER TABLE messages_whatsapp
RENAME COLUMN function_name TO tool_name;

-- Add tool_details column to messages / messages_whatsapp tables
-- NOTE: Check out the `tool_details` variable in `process_one_round()` in `ansari.py` 
--  to see the structure of the JSON stored in this column
ALTER TABLE messages
ADD COLUMN tool_details JSONB DEFAULT '{}'::jsonb;

ALTER TABLE messages_whatsapp
ADD COLUMN tool_details JSONB DEFAULT '{}'::jsonb;