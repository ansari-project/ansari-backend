-- This script transforms the users table's primary key from an integer-based ID to a UUID
-- It also updates all foreign key references across the database to maintain data integrity
-- The entire process runs in a transaction to ensure all changes succeed or none do

-- Start a transaction to ensure atomicity
BEGIN;

-- Enable UUID extension if not already available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Step 1: Add a new UUID column to the users table to hold the new IDs
ALTER TABLE users ADD COLUMN new_id UUID DEFAULT uuid_generate_v4() NOT NULL;

-- Step 2: Generate unique UUIDs for each existing user
UPDATE users SET new_id = uuid_generate_v4();

-- Step 3: For each table that references users.id, migrate the foreign key from INTEGER to UUID
-- This anonymous PL/pgSQL block dynamically processes each related table
DO $$
DECLARE
  table_name TEXT;
  -- Define all tables that have a foreign key to users.id
  tables CURSOR FOR
    SELECT unnest(ARRAY['preferences', 'feedback', 'messages', 'threads', 'users_whatsapp', 'access_tokens', 'refresh_tokens', 'reset_tokens']) AS table_name;
BEGIN
  FOR table_info IN tables LOOP
  RAISE NOTICE 'Updating % table', table_info.table_name;

    -- Step 3a: Add a new UUID column to hold the new foreign key values
	EXECUTE format('ALTER TABLE %I ADD COLUMN new_user_id UUID NULL;', table_info.table_name);
    
    -- Step 3b: Copy the foreign key relationship using the new UUID values
	EXECUTE format('UPDATE %I t SET new_user_id = u.new_id FROM users u WHERE t.user_id = u.id;', table_info.table_name);
    
    -- Step 3c: Make the new column non-nullable once data is migrated
	EXECUTE format('ALTER TABLE %I ALTER COLUMN new_user_id SET NOT NULL;', table_info.table_name);

    -- Step 3d: Remove the old foreign key constraint
	EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I_user_id_fkey;', table_info.table_name, table_info.table_name);
    
    -- Step 3e: Remove the old integer column
	EXECUTE format('ALTER TABLE %I DROP COLUMN user_id;', table_info.table_name);
    
    -- Step 3f: Rename the new UUID column to the original column name
	EXECUTE format('ALTER TABLE %I RENAME COLUMN new_user_id TO user_id;', table_info.table_name);

  RAISE NOTICE 'Completed updating % table', table_info.table_name;
  END LOOP;
END $$;

-- Step 4: Update the users table primary key
-- Step 4a: Remove the existing primary key constraint
ALTER TABLE users DROP CONSTRAINT users_pkey;

-- Step 4b: Remove the old ID column
ALTER TABLE users DROP COLUMN id;

-- Step 4c: Rename the new UUID column to 'id'
ALTER TABLE users RENAME COLUMN new_id TO id;

-- Step 4d: Set the new UUID column as primary key
ALTER TABLE users ADD PRIMARY KEY (id);

-- Step 4e: Set the default value for new users to auto-generate UUIDs
ALTER TABLE users ALTER COLUMN id SET DEFAULT uuid_generate_v4();

-- Step 5: Reestablish all foreign key relationships with the new UUID primary key
DO $$
DECLARE
  table_name TEXT;
  tables CURSOR FOR
    SELECT unnest(ARRAY['preferences', 'feedback', 'messages', 'threads', 'users_whatsapp', 'access_tokens', 'refresh_tokens', 'reset_tokens']) AS table_name;
BEGIN
  FOR table_info IN tables LOOP
  RAISE NOTICE 'Updating % table', table_info.table_name;

    -- Add back the foreign key constraints to reference the new UUID primary key
	EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);', table_info.table_name, table_info.table_name);

  RAISE NOTICE 'Completed updating % table', table_info.table_name;
  END LOOP;
END $$;

-- Commit all changes if everything succeeded
COMMIT;

-- In case of any failure, all changes will be rolled back
-- ROLLBACK; -- Uncomment this line if executing manually and an error occurs