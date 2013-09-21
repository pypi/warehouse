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
        # CREATE the citext extension
        db.execute("CREATE EXTENSION IF NOT EXISTS citext")

        # Adding model 'Project'
        db.create_table('packages_project', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('warehouse.utils.db_fields.CaseInsensitiveTextField')(unique=True)),
            ('normalized', self.gf('warehouse.utils.db_fields.CaseInsensitiveTextField')(blank=True, unique=True)),
            ('autohide', self.gf('django.db.models.fields.BooleanField')(default=True)),
            ('bugtrack_url', self.gf('warehouse.utils.db_fields.URLTextField')(blank=True)),
            ('hosting_mode', self.gf('django.db.models.fields.CharField')(default='pypi-explicit', max_length=20)),
        ))

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
            ADD CONSTRAINT packages_project_valid_name
            CHECK (
               normalized ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'
            )
        """)

        db.send_create_signal('packages', ['Project'])

    def backwards(self, orm):
        # Deleting model 'Project'
        db.delete_table('packages_project')

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
