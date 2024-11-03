UPDATE users 
SET 
    is_guest = TRUE,
    updated_at = CURRENT_TIMESTAMP
WHERE 
    email LIKE 'guest_%@endeavorpal.com'
    AND first_name = 'Welcome'
    AND last_name = 'Guest';
