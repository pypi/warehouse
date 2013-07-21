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

-- Start a transaction to contain all the changes
BEGIN;

-- Make sure nobody is touching the users table but us
LOCK TABLE users IN ACCESS EXCLUSIVE MODE;

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

-- For each user with a gpg_keyid create an accounts_gpgkey row
INSERT INTO accounts_gpgkey
    (user_id, key_id, verified)
SELECT DISTINCT ON (users.gpg_keyid)
    accounts_user.id, users.gpg_keyid, FALSE
FROM users, accounts_user
WHERE
        users.name = accounts_user.username
    AND users.gpg_keyid IS NOT NULL
    AND users.gpg_keyid ~* '^[A-F0-9]{8}$';

-- Set every user with the Admin role to a staff member and superadmin
UPDATE accounts_user
SET
    is_staff = TRUE, is_superuser = TRUE
FROM roles
WHERE roles.role_name = 'Admin' AND accounts_user.username = roles.user_name;

-- Rewrite ForeignKey Constraints to point towards accounts_user
ALTER TABLE rego_otk DROP CONSTRAINT "$1";
ALTER TABLE rego_otk ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE rego_otk
    ADD FOREIGN KEY (name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE CASCADE;

ALTER TABLE comments_journal
    DROP CONSTRAINT comments_journal_submitted_by_fkey;
ALTER TABLE comments_journal
    ALTER COLUMN submitted_by TYPE citext USING submitted_by::citext;
ALTER TABLE comments_journal
    ADD FOREIGN KEY (submitted_by)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE CASCADE;

ALTER TABLE comments DROP CONSTRAINT comments_user_name_fkey;
ALTER TABLE comments
    ALTER COLUMN user_name TYPE citext USING user_name::citext;
ALTER TABLE comments
    ADD FOREIGN KEY (user_name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE CASCADE;

ALTER TABLE cookies DROP CONSTRAINT cookies_name_fkey;
ALTER TABLE cookies ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE cookies
    ADD FOREIGN KEY (name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE CASCADE;

ALTER TABLE csrf_tokens DROP CONSTRAINT csrf_tokens_name_fkey;
ALTER TABLE csrf_tokens ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE csrf_tokens
    ADD FOREIGN KEY (name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE CASCADE;

ALTER TABLE journals DROP CONSTRAINT journals_submitted_by_fkey;
ALTER TABLE journals
    ALTER COLUMN submitted_by TYPE citext USING submitted_by::citext;
ALTER TABLE journals
    ADD FOREIGN KEY (submitted_by)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE NO ACTION;

ALTER TABLE mirrors DROP CONSTRAINT mirrors_user_name_fkey;
ALTER TABLE mirrors
    ALTER COLUMN user_name TYPE citext USING user_name::citext;
ALTER TABLE mirrors
    ADD FOREIGN KEY (user_name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;

ALTER TABLE oauth_access_tokens
    DROP CONSTRAINT oauth_access_tokens_user_name_fkey;
ALTER TABLE oauth_access_tokens
    ALTER COLUMN user_name TYPE citext USING user_name::citext;
ALTER TABLE oauth_access_tokens
    ADD FOREIGN KEY (user_name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE CASCADE;

ALTER TABLE oauth_consumers
    DROP CONSTRAINT oauth_consumers_created_by_fkey;
ALTER TABLE oauth_consumers
    ALTER COLUMN created_by TYPE citext USING created_by::citext;
ALTER TABLE oauth_consumers
    ADD FOREIGN KEY (created_by)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE NO ACTION;

ALTER TABLE oauth_request_tokens
    DROP CONSTRAINT oauth_request_tokens_user_name_fkey;
ALTER TABLE oauth_request_tokens
    ALTER COLUMN user_name TYPE citext USING user_name::citext;
ALTER TABLE oauth_request_tokens
    ADD FOREIGN KEY (user_name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE CASCADE;

ALTER TABLE openids DROP CONSTRAINT openids_name_fkey;
ALTER TABLE openids ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE openids
    ADD FOREIGN KEY (name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE CASCADE;

ALTER TABLE ratings DROP CONSTRAINT ratings_user_name_fkey;
ALTER TABLE ratings ALTER COLUMN user_name TYPE citext USING user_name::citext;
ALTER TABLE ratings
    ADD FOREIGN KEY (user_name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE CASCADE;

ALTER TABLE roles DROP CONSTRAINT roles_user_name_fkey;
ALTER TABLE roles ALTER COLUMN user_name TYPE citext USING user_name::citext;
ALTER TABLE roles
    ADD FOREIGN KEY (user_name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE NO ACTION;

ALTER TABLE sshkeys DROP CONSTRAINT sshkeys_name_fkey;
ALTER TABLE sshkeys ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE sshkeys
    ADD FOREIGN KEY (name)
    REFERENCES accounts_user (username)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE CASCADE;

-- Delete the users table now that it has been converted
DROP TABLE users;

-- Save the work
COMMIT;
