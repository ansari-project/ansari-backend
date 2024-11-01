-- Set is_guest field for users with NULL emails or emails containing 'guest'
UPDATE users
SET is_guest = CASE
    WHEN email IS NULL OR email ILIKE '%guest%' THEN TRUE
    ELSE FALSE
END;
