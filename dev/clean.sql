\set ON_ERROR_STOP on

-- Set all of the email addresses to a random value so we don't leak people's
-- email addresses.
UPDATE user_emails
    SET email = encode(gen_random_bytes(16), 'hex') || '@example.com';


-- Set all of our passwords to use the password 'password', hashed with bcrypt,
-- as well as setting the last_login and date_joined to today.
-- remove TOTP data.
UPDATE users
    SET password = 'bcrypt$$2a$16$xq9g/NAFoiOtFkGpk/kgjOiPDPs1/pMG0GHeDHWHSOd9IY7Fah.yC',
        last_login = now(),
        date_joined = now(),
        totp_secret = NULL,
        last_totp_value = NULL;

-- Remove Squats data
DELETE FROM admin_squats;

-- Remove Recovery Codes
DELETE FROM user_recovery_codes;

-- Remove WebAuthn keys
DELETE FROM user_security_keys;
-- Remove API tokens
DELETE FROM macaroons;

-- Remove any personally identifying information from journals
ALTER TABLE journals DISABLE TRIGGER ALL;
UPDATE journals SET submitted_by = 'dstufft', submitted_from = '127.0.0.1';
ALTER TABLE journals ENABLE TRIGGER ALL;

-- Remove user and project journals
DELETE FROM user_events;
DELETE FROM project_events;

-- Remove malware checks and verdicts
DELETE FROM malware_checks;
DELETE FROM malware_verdicts;

-- Remove email logs
DELETE FROM ses_events;
DELETE FROM ses_emails;
