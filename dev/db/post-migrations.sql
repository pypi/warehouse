-- Set password to 'password' hashed with argon
UPDATE users SET password = '$argon2id$v=19$m=1024,t=6,p=6$EiLE2Nsbo9S6N+acs/beGw$ccyZDCZstr1/+Y/1s3BVZHOJaqfBroT0JCieHug281c';

-- Create Recovery Codes for select users

-- 6ebc846aadf23e35
-- 7283821faf191a33
-- 68108e19d25e2eec
-- 4e6a18adb880fbc1
-- f62627d29675725f
-- 4cda895a133b4cc8
-- 8678c6f0d9a1e6de
-- edc6ce3800c0fc94 -- burned

INSERT INTO user_recovery_codes (user_id, code, generated, burned)
VALUES
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$ovSeMyakdM75HyOEkJIyBg$IkeTs3Bi++VEU16dFOC9cfyAhQ2/hzjyfStgahmcsS0', '2024-07-11 12:56:05.531627', NULL),
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$836v9R5DSGnNWYtRqjXmvA$Evsz90W4sWZU+AyF4EmAk6wlJSxySGRBO9lE4fmqIqA', '2024-07-11 12:56:05.531627', NULL),
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$C0EIodR6DyGkVCqltLbWeg$gbM5iglbcGkkBWzz6GXapwg7q92O6bfP7WWDNp0Q/gQ', '2024-07-11 12:56:05.531627', NULL),
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$ee/9H6MUAkBoTUkJgRDCmA$GmIdBAuAhVmLBPt9106dHLxjXn88KTRjnmdgMb+ZX94', '2024-07-11 12:56:05.531627', NULL),
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$EcKY855zTmnt3ft/DyEEoA$p3pybB5dMhQgmxdNgPXBRuBy3myEQUYRhB2ubcYrv4w', '2024-07-11 12:56:05.531627', NULL),
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$u9caQ+g9J+R8b815T+m9Vw$nkr68rHKcRGku1BAuQQo2V1DNmIZKp6sTFs0kqq3xh4', '2024-07-11 12:56:05.531627', NULL),
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$dY5x7p3TGoOw9v5f6/0/hw$mHDJOfdPWoPf7YO4Jlqzu4zXvPIm1P4ReR9Ch1JmoFc', '2024-07-11 12:56:05.531627', NULL),
 ('70713e05-0f9c-4f30-8899-3c4e8d55e77c', '$argon2id$v=19$m=1024,t=6,p=6$P4dwzjnnvBdCqHUOQaiV8g$OyyWuG5X+AD2YRoG0vMQc7nUmpzxCPb/IfwClAdOrfA', '2024-07-11 12:56:05.531627', '2024-07-11 12:56:15.893001'),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$ovSeMyakdM75HyOEkJIyBg$IkeTs3Bi++VEU16dFOC9cfyAhQ2/hzjyfStgahmcsS0', '2024-07-11 12:56:05.531627', NULL),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$836v9R5DSGnNWYtRqjXmvA$Evsz90W4sWZU+AyF4EmAk6wlJSxySGRBO9lE4fmqIqA', '2024-07-11 12:56:05.531627', NULL),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$C0EIodR6DyGkVCqltLbWeg$gbM5iglbcGkkBWzz6GXapwg7q92O6bfP7WWDNp0Q/gQ', '2024-07-11 12:56:05.531627', NULL),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$ee/9H6MUAkBoTUkJgRDCmA$GmIdBAuAhVmLBPt9106dHLxjXn88KTRjnmdgMb+ZX94', '2024-07-11 12:56:05.531627', NULL),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$EcKY855zTmnt3ft/DyEEoA$p3pybB5dMhQgmxdNgPXBRuBy3myEQUYRhB2ubcYrv4w', '2024-07-11 12:56:05.531627', NULL),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$u9caQ+g9J+R8b815T+m9Vw$nkr68rHKcRGku1BAuQQo2V1DNmIZKp6sTFs0kqq3xh4', '2024-07-11 12:56:05.531627', NULL),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$dY5x7p3TGoOw9v5f6/0/hw$mHDJOfdPWoPf7YO4Jlqzu4zXvPIm1P4ReR9Ch1JmoFc', '2024-07-11 12:56:05.531627', NULL),
 ('d26ebd95-4d49-4534-ae6e-69b3bce9721c', '$argon2id$v=19$m=1024,t=6,p=6$P4dwzjnnvBdCqHUOQaiV8g$OyyWuG5X+AD2YRoG0vMQc7nUmpzxCPb/IfwClAdOrfA', '2024-07-11 12:56:05.531627', '2024-07-11 12:56:15.893001'),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$ovSeMyakdM75HyOEkJIyBg$IkeTs3Bi++VEU16dFOC9cfyAhQ2/hzjyfStgahmcsS0', '2024-07-11 12:56:05.531627', NULL),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$836v9R5DSGnNWYtRqjXmvA$Evsz90W4sWZU+AyF4EmAk6wlJSxySGRBO9lE4fmqIqA', '2024-07-11 12:56:05.531627', NULL),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$C0EIodR6DyGkVCqltLbWeg$gbM5iglbcGkkBWzz6GXapwg7q92O6bfP7WWDNp0Q/gQ', '2024-07-11 12:56:05.531627', NULL),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$ee/9H6MUAkBoTUkJgRDCmA$GmIdBAuAhVmLBPt9106dHLxjXn88KTRjnmdgMb+ZX94', '2024-07-11 12:56:05.531627', NULL),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$EcKY855zTmnt3ft/DyEEoA$p3pybB5dMhQgmxdNgPXBRuBy3myEQUYRhB2ubcYrv4w', '2024-07-11 12:56:05.531627', NULL),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$u9caQ+g9J+R8b815T+m9Vw$nkr68rHKcRGku1BAuQQo2V1DNmIZKp6sTFs0kqq3xh4', '2024-07-11 12:56:05.531627', NULL),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$dY5x7p3TGoOw9v5f6/0/hw$mHDJOfdPWoPf7YO4Jlqzu4zXvPIm1P4ReR9Ch1JmoFc', '2024-07-11 12:56:05.531627', NULL),
 ('f90a82e1-1a1a-45cd-a1ca-53a033d0f867', '$argon2id$v=19$m=1024,t=6,p=6$P4dwzjnnvBdCqHUOQaiV8g$OyyWuG5X+AD2YRoG0vMQc7nUmpzxCPb/IfwClAdOrfA', '2024-07-11 12:56:05.531627', '2024-07-11 12:56:15.893001'),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$ovSeMyakdM75HyOEkJIyBg$IkeTs3Bi++VEU16dFOC9cfyAhQ2/hzjyfStgahmcsS0', '2024-07-11 12:56:05.531627', NULL),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$836v9R5DSGnNWYtRqjXmvA$Evsz90W4sWZU+AyF4EmAk6wlJSxySGRBO9lE4fmqIqA', '2024-07-11 12:56:05.531627', NULL),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$C0EIodR6DyGkVCqltLbWeg$gbM5iglbcGkkBWzz6GXapwg7q92O6bfP7WWDNp0Q/gQ', '2024-07-11 12:56:05.531627', NULL),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$ee/9H6MUAkBoTUkJgRDCmA$GmIdBAuAhVmLBPt9106dHLxjXn88KTRjnmdgMb+ZX94', '2024-07-11 12:56:05.531627', NULL),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$EcKY855zTmnt3ft/DyEEoA$p3pybB5dMhQgmxdNgPXBRuBy3myEQUYRhB2ubcYrv4w', '2024-07-11 12:56:05.531627', NULL),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$u9caQ+g9J+R8b815T+m9Vw$nkr68rHKcRGku1BAuQQo2V1DNmIZKp6sTFs0kqq3xh4', '2024-07-11 12:56:05.531627', NULL),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$dY5x7p3TGoOw9v5f6/0/hw$mHDJOfdPWoPf7YO4Jlqzu4zXvPIm1P4ReR9Ch1JmoFc', '2024-07-11 12:56:05.531627', NULL),
 ('d8f60fd2-79a7-47a6-82a2-fdbd12af2cab', '$argon2id$v=19$m=1024,t=6,p=6$P4dwzjnnvBdCqHUOQaiV8g$OyyWuG5X+AD2YRoG0vMQc7nUmpzxCPb/IfwClAdOrfA', '2024-07-11 12:56:05.531627', '2024-07-11 12:56:15.893001');

-- Set TOTP secret to IU7UP3EMIPI7EBPQUUSEHEJUFNBIWOYG for select users
UPDATE users SET totp_secret = '\x453f47ec8c43d1f205f0a5244391342b428b3b06' WHERE username IN ('ewdurbin', 'di', 'dstufft', 'miketheman');
