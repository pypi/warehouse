#!/bin/bash
set -e

psql -d "$POSTGRES_DB" -U "$POSTGRES_USER" <<-EOF
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname ='warehouse';
    DROP DATABASE IF EXISTS warehouse;
    CREATE DATABASE warehouse ENCODING 'UTF8';
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname ='rstuf';
    DROP DATABASE IF EXISTS rstuf;
    CREATE DATABASE rstuf ENCODING 'UTF8';
EOF

xz -d -f -k /example.sql.xz --stdout | psql -d warehouse -U "$POSTGRES_USER" -v ON_ERROR_STOP=1 -1 -f -

psql -d warehouse -U "$POSTGRES_USER" <<-EOF
    UPDATE users SET name='Ee Durbin' WHERE username='ewdurbin';
EOF
