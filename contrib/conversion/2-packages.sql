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

-- Make sure nobody is touching the packages table but us
LOCK TABLE packages IN ACCESS EXCLUSIVE MODE;

-- Set bugtrack_url to '' wherever it's NULL because Django uses '' instead of
--  NULL
UPDATE packages SET bugtrack_url = '' WHERE bugtrack_url IS NULL;

-- Copy over the projects from packages to packages_project
INSERT INTO packages_project (name, autohide, bugtrack_url, hosting_mode)
SELECT name, autohide, bugtrack_url, hosting_mode
    FROM packages;

-- Rewrite ForeignKey Constraints to point towards packages_project
ALTER TABLE comments_journal ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE description_urls ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE ratings ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE release_classifiers ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE release_dependencies ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE release_files ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE release_requires_python ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE release_urls ALTER COLUMN name TYPE citext USING name::citext;

ALTER TABLE releases DROP CONSTRAINT releases_name_fkey;
ALTER TABLE releases ALTER COLUMN name TYPE citext USING name::citext;
ALTER TABLE releases
    ADD FOREIGN KEY (name)
    REFERENCES packages_project (name)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE NO ACTION;

ALTER TABLE roles DROP CONSTRAINT roles_package_name_fkey;
ALTER TABLE roles ALTER COLUMN package_name TYPE citext USING package_name::citext;
ALTER TABLE roles
    ADD FOREIGN KEY (package_name)
    REFERENCES packages_project (name)
    MATCH SIMPLE
    ON UPDATE CASCADE
    ON DELETE NO ACTION;

-- Delete the packages table now that it has been converted
DROP TABLE packages;

-- Save the work
COMMIT;
