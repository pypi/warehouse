\set ON_ERROR_STOP on

-- Set all of the email addresses to a random value so we don't leak people's
-- email addresses.
UPDATE accounts_email
    SET email = encode(gen_random_bytes(16), 'md5'), 'hex') || '@example.com';


-- Set all of our passwords to use the password 'password', hashed with bcrypt,
-- as well as setting the last_login and date_joined to today.
UPDATE accounts_user
    SET password = 'bcrypt$$2a$16$xq9g/NAFoiOtFkGpk/kgjOiPDPs1/pMG0GHeDHWHSOd9IY7Fah.yC',
        last_login = now(),
        date_joined = now();

-- Not sure what these values are exactly, will remove them to be safe.
UPDATE releases SET cheesecake_installability_id = NULL,
                    cheesecake_documentation_id = NULL,
                    cheesecake_code_kwalitee_id = NULL;
DELETE FROM browse_tally;
DELETE FROM cheesecake_subindices;
DELETE FROM cheesecake_main_indices;
DELETE FROM comments;
DELETE FROM comments_journal;
DELETE FROM cookies;
DELETE FROM csrf_tokens;
DELETE FROM oauth_access_tokens;
DELETE FROM oauth_consumers;
DELETE FROM oauth_nonce;
DELETE FROM oauth_request_tokens;
DELETE FROM oid_associations;
DELETE FROM oid_nonces;
DELETE FROM openid_discovered;
DELETE FROM openid_nonces;
DELETE FROM openid_sessions;
DELETE FROM openid_whitelist;
DELETE FROM openids;
DELETE FROM ratings;
DELETE FROM rego_otk;
DELETE FROM sshkeys;
DELETE FROM timestamps;


-- Remove any personally identifying information from journals
UPDATE journals SET submitted_by = 'dstufft', submitted_from = '127.0.0.1';
