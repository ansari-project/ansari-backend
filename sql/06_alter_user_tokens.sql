BEGIN;
ALTER TABLE user_tokens DROP CONSTRAINT user_tokens_pkey;
ALTER TABLE user_tokens ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE user_tokens ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE user_tokens RENAME TO access_tokens;
ALTER TABLE access_tokens ADD CONSTRAINT access_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE access_tokens ADD COLUMN id SERIAL PRIMARY KEY;
COMMIT;