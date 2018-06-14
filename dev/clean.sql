\set ON_ERROR_STOP on

-- Set all of the email addresses to a random value so we don't leak people's
-- email addresses.
UPDATE accounts_email
    SET email = encode(gen_random_bytes(16), 'hex') || '@example.com';


-- Set all of our passwords to use the password 'password', hashed with bcrypt,
-- as well as setting the last_login and date_joined to today.
UPDATE accounts_user
    SET password = 'bcrypt$$2a$16$xq9g/NAFoiOtFkGpk/kgjOiPDPs1/pMG0GHeDHWHSOd9IY7Fah.yC',
        last_login = now(),
        date_joined = now();

DELETE FROM rego_otk;


-- Remove any personally identifying information from journals
ALTER TABLE journals DISABLE TRIGGER ALL;
UPDATE journals SET submitted_by = 'dstufft', submitted_from = '127.0.0.1';
ALTER TABLE journals ENABLE TRIGGER ALL;
