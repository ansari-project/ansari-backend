-- NOTE: This is a temporary script that will be used for prod's DB, then deleted

-- Start a transaction to ensure atomicity
BEGIN;

-- This script changes the 'id' column of the 'users' table from an integer to a UUID

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

ALTER TABLE users ADD COLUMN new_id UUID DEFAULT uuid_generate_v4() NOT NULL;

UPDATE users SET new_id = uuid_generate_v4();

DO $$
DECLARE
  table_name TEXT;
  tables CURSOR FOR
    SELECT unnest(ARRAY['preferences', 'feedback', 'messages', 'threads', 'users_whatsapp', 'access_tokens', 'refresh_tokens', 'reset_tokens']) AS table_name;
BEGIN
  FOR table_info IN tables LOOP
  RAISE NOTICE 'Updating % table', table_info.table_name;

	EXECUTE format('ALTER TABLE %I ADD COLUMN new_user_id UUID NULL;', table_info.table_name);
	EXECUTE format('UPDATE %I t SET new_user_id = u.new_id FROM users u WHERE t.user_id = u.id;', table_info.table_name);
	EXECUTE format('ALTER TABLE %I ALTER COLUMN new_user_id SET NOT NULL;', table_info.table_name);

	EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I_user_id_fkey;', table_info.table_name, table_info.table_name);
	EXECUTE format('ALTER TABLE %I DROP COLUMN user_id;', table_info.table_name);
	EXECUTE format('ALTER TABLE %I RENAME COLUMN new_user_id TO user_id;', table_info.table_name);

  RAISE NOTICE 'Completed updating % table', table_info.table_name;
  END LOOP;
END $$;

ALTER TABLE users DROP CONSTRAINT users_pkey;

ALTER TABLE users DROP COLUMN id;

ALTER TABLE users RENAME COLUMN new_id TO id;

ALTER TABLE users ADD PRIMARY KEY (id);

ALTER TABLE users ALTER COLUMN id SET DEFAULT uuid_generate_v4();

DO $$
DECLARE
  table_name TEXT;
  tables CURSOR FOR
    SELECT unnest(ARRAY['preferences', 'feedback', 'messages', 'threads', 'users_whatsapp', 'access_tokens', 'refresh_tokens', 'reset_tokens']) AS table_name;
BEGIN
  FOR table_info IN tables LOOP
  RAISE NOTICE 'Updating % table', table_info.table_name;

	EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);', table_info.table_name, table_info.table_name);

  RAISE NOTICE 'Completed updating % table', table_info.table_name;
  END LOOP;
END $$;


-- Commit the transaction if all operations succeed
COMMIT;

-- In case of any failure, all changes will be rolled back
-- ROLLBACK; -- Uncomment this line if executing manually and an error occurs