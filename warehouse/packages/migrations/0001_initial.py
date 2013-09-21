# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Project'
        db.create_table('packages_project', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('warehouse.utils.db_fields.CaseInsensitiveTextField')(unique=True)),
            ('normalized', self.gf('warehouse.utils.db_fields.CaseInsensitiveTextField')(blank=True, unique=True)),
            ('autohide', self.gf('django.db.models.fields.BooleanField')(default=True)),
            ('bugtrack_url', self.gf('warehouse.utils.db_fields.URLTextField')(blank=True)),
            ('hosting_mode', self.gf('django.db.models.fields.CharField')(default='pypi-explicit', max_length=20)),
        ))

        # Adding uniqueness constraint on 'Project.name' that considers the
        #   equivalent characters equivalent.
        # Currently this includes hard coded exceptions for packages that
        #   already violate this rule in the PyPI code base. At some point in
        #   time it would be great to get rid of these.
        db.execute("""
            CREATE UNIQUE INDEX packages_project_name_unique_idx
            ON packages_project
            (
                regexp_replace(
                    regexp_replace(
                        regexp_replace(name, '_', '-', 'ig'),
                        '[1L]', 'I', 'ig'
                    ),
                    '0', 'O', 'ig'
                )
            )
            WHERE name NOT IN (
                'cali', 'call', 'PIL', 'pli', 'dlx', 'dix', 'Pylon', 'pyion',
                'pylo', 'pyio', 'ixml', 'lxml', 'xi', 'xl', 'pydl', 'pydi',
                'KLM', 'kim', 'tdl', 'tdi', 'si', 'sl', 'ply', 'piy', 'hello',
                'helio', 'pyple', 'pypie', 'doit', 'Dolt', 'PySLIC', 'pysilc',
                'SCons', 'sc0ns', 'ldb', 'iDB', 'IMDb', 'lmdb', 'uri', 'url',
                'islpy', 'ISIpy', 'node.ext.xmi', 'node.ext.xml', 'pyaml',
                'pyami', 'FIAT', 'flat', 'pyli', 'Pyll', 'lpy', 'IPy', 'pysl',
                'pysi'
            )
        """)

        # Adding uniqueness constraint on 'Project.normalized' that considers
        #   the equivalent characters equivalent.
        # Currently this includes hard coded exceptions for packages that
        #   already violate this rule in the PyPI code base. At some point in
        #   time it would be great to get rid of these.
        db.execute("""
            CREATE UNIQUE INDEX packages_project_normalized_unique_idx
            ON packages_project
            (
                regexp_replace(
                    regexp_replace(
                        regexp_replace(normalized, '_', '-', 'ig'),
                        '[1L]', 'I', 'ig'
                    ),
                    '0', 'O', 'ig'
                )
            )
            WHERE name NOT IN (
                'cali', 'call', 'PIL', 'pli', 'dlx', 'dix', 'Pylon', 'pyion',
                'pylo', 'pyio', 'ixml', 'lxml', 'xi', 'xl', 'pydl', 'pydi',
                'KLM', 'kim', 'tdl', 'tdi', 'si', 'sl', 'ply', 'piy', 'hello',
                'helio', 'pyple', 'pypie', 'doit', 'Dolt', 'PySLIC', 'pysilc',
                'SCons', 'sc0ns', 'ldb', 'iDB', 'IMDb', 'lmdb', 'uri', 'url',
                'islpy', 'ISIpy', 'node.ext.xmi', 'node.ext.xml', 'pyaml',
                'pyami', 'FIAT', 'flat', 'pyli', 'Pyll', 'lpy', 'IPy', 'pysl',
                'pysi'
            )
        """)

        # Adding valid name constraint on 'Project'
        db.execute("""
            ALTER TABLE packages_project
            ADD CONSTRAINT packages_project_valid_name
            CHECK (
               name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'
            )
        """)

        # Adding valid normalized constraint on 'Project'
        db.execute("""
            ALTER TABLE packages_project
            ADD CONSTRAINT packages_project_valid_normalized
            CHECK (
               normalized ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'
            )
        """)

        # Adding a trigger to ensure that the normalized field stays populated
        db.execute("""
            CREATE OR REPLACE FUNCTION normalize_name_trigger()
            RETURNS trigger AS $$
            BEGIN
                NEW.normalized = regexp_replace(NEW.name, '_', '-', 'ig');
                return NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        db.execute("""
            CREATE TRIGGER packages_project_normalize_name
            BEFORE INSERT OR UPDATE
            ON packages_project
            FOR EACH ROW
            EXECUTE PROCEDURE normalize_name_trigger();
        """)

        db.send_create_signal('packages', ['Project'])

    def backwards(self, orm):
        # Deleting model 'Project'
        db.delete_table('packages_project')

        # Delete the normalize_name_trigger function
        db.execute("DROP FUNCTION normalize_name_trigger()")

    models = {
        'packages.project': {
            'Meta': {'object_name': 'Project'},
            'autohide': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'bugtrack_url': ('warehouse.utils.db_fields.URLTextField', [], {'blank': 'True'}),
            'hosting_mode': ('django.db.models.fields.CharField', [], {'default': "'pypi-explicit'", 'max_length': '20'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('warehouse.utils.db_fields.CaseInsensitiveTextField', [], {'unique': 'True'}),
            'normalized': ('warehouse.utils.db_fields.CaseInsensitiveTextField', [], {'blank': 'True', 'unique': 'True'})
        }
    }

    complete_apps = ['packages']
