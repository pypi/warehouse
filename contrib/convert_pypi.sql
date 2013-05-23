-- Copyright 2013 Donald Stufft
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Make sure there is a value in every last_login field
UPDATE users SET last_login = '-infinity' WHERE last_login IS NULL;

-- Copy over the users from users to accounts_user
INSERT INTO accounts_user
    (username, password, last_login, is_active, is_staff, is_superuser, name, date_joined)
SELECT name, password, last_login, TRUE, FALSE, FALSE, '', '-infinity'
    FROM users;

-- Update the password to use the Django style passwords
UPDATE accounts_user SET password = 'bcrypt$' || password WHERE password LIKE '$2a$%';

-- For each user with an email, create an accounts_email row
INSERT INTO accounts_email
    (user_id, email, "primary", verified)
SELECT DISTINCT ON (users.email)
    accounts_user.id, users.email, TRUE, TRUE
FROM users, accounts_user
WHERE users.name = accounts_user.username AND users.email IS NOT NULL;

-- Set every user with the Admin role to a staff member and superadmin
UPDATE accounts_user
SET
    is_staff = TRUE, is_superuser = TRUE
FROM roles
WHERE roles.role_name = 'Admin' AND accounts_user.username = roles.user_name;
