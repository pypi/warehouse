-- Set password to 'password' hashed with argon
UPDATE users SET password = '$argon2id$v=19$m=1024,t=6,p=6$EiLE2Nsbo9S6N+acs/beGw$ccyZDCZstr1/+Y/1s3BVZHOJaqfBroT0JCieHug281c';

-- Set TOTP secret to IU7UP3EMIPI7EBPQUUSEHEJUFNBIWOYG for select users
UPDATE users SET totp_secret = '\x453f47ec8c43d1f205f0a5244391342b428b3b06' WHERE username IN ('ewdurbin', 'di', 'dstufft', 'miketheman');
