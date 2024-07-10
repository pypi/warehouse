-- Set password to 'password' hashed with argon
UPDATE users SET password = '$argon2id$v=19$m=1024,t=6,p=6$EiLE2Nsbo9S6N+acs/beGw$ccyZDCZstr1/+Y/1s3BVZHOJaqfBroT0JCieHug281c';
