-- Add ref_list column to messages table
ALTER TABLE messages
ADD COLUMN ref_list JSONB;

-- Add ref_list column to messages_whatsapp table
ALTER TABLE messages_whatsapp
ADD COLUMN ref_list JSONB;

-- Add comment to explain the column
COMMENT ON COLUMN messages.ref_list IS 'JSON array containing reference list data for tool responses';
COMMENT ON COLUMN messages_whatsapp.ref_list IS 'JSON array containing reference list data for tool responses';
