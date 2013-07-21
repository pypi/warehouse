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
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # CREATE the citext extension
        db.execute("CREATE EXTENSION IF NOT EXISTS citext")

        # Adding model 'User'
        db.create_table('accounts_user', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('password', self.gf('django.db.models.fields.CharField')(max_length=128)),
            ('last_login', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now)),
            ('is_superuser', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('username', self.gf('warehouse.utils.db_fields.CaseInsensitiveCharField')(unique=True, max_length=50)),
            ('name', self.gf('django.db.models.fields.CharField')(blank=True, max_length=100)),
            ('is_staff', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('is_active', self.gf('django.db.models.fields.BooleanField')(default=True)),
            ('date_joined', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now)),
        ))

        # Adding constraint to model field 'User.username'
        db.execute("""
            ALTER TABLE accounts_user
            ADD CONSTRAINT accounts_user_username_length
            CHECK (
                length(username) <= 50
            )
        """)

        # Adding valid username constraint on 'User'
        db.execute("""
            ALTER TABLE accounts_user
            ADD CONSTRAINT accounts_user_valid_username
            CHECK (
                username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'
            )
        """)

        # Send signal to show we've created the User model
        db.send_create_signal('accounts', ['User'])

        # Adding M2M table for field groups on 'User'
        m2m_table_name = db.shorten_name('accounts_user_groups')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('user', models.ForeignKey(orm['accounts.user'], null=False)),
            ('group', models.ForeignKey(orm['auth.group'], null=False))
        ))
        db.create_unique(m2m_table_name, ['user_id', 'group_id'])

        # Adding M2M table for field user_permissions on 'User'
        m2m_table_name = db.shorten_name('accounts_user_user_permissions')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('user', models.ForeignKey(orm['accounts.user'], null=False)),
            ('permission', models.ForeignKey(orm['auth.permission'], null=False))
        ))
        db.create_unique(m2m_table_name, ['user_id', 'permission_id'])

        # Adding model 'Email'
        db.create_table('accounts_email', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(related_name='emails', to=orm['accounts.User'], on_delete=models.DO_NOTHING)),
            ('email', self.gf('django.db.models.fields.EmailField')(unique=True, max_length=254)),
            ('primary', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('verified', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal('accounts', ['Email'])

        # Adding model 'GPGKey'
        db.create_table('accounts_gpgkey', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(related_name='gpg_keys', to=orm['accounts.User'], on_delete=models.DO_NOTHING)),
            ('key_id', self.gf('warehouse.utils.db_fields.CaseInsensitiveCharField')(unique=True, max_length=16)),
        ))

        # Adding valid key_id constraint on 'GPGKey'
        db.execute("""
            ALTER TABLE accounts_gpgkey
            ADD CONSTRAINT accounts_gpgkey_valid_key_id
            CHECK (
                key_id ~* '^[A-F0-9]{16}$'
            )
        """)

        # Send signal to show we've created the GPGKey model
        db.send_create_signal('accounts', ['GPGKey'])

    def backwards(self, orm):
        # Deleting model 'User'
        db.delete_table('accounts_user')

        # Removing M2M table for field groups on 'User'
        db.delete_table(db.shorten_name('accounts_user_groups'))

        # Removing M2M table for field user_permissions on 'User'
        db.delete_table(db.shorten_name('accounts_user_user_permissions'))

        # Deleting model 'Email'
        db.delete_table('accounts_email')

        # Deleting model 'GPGKey'
        db.delete_table('accounts_gpgkey')

    models = {
        'accounts.email': {
            'Meta': {'object_name': 'Email'},
            'email': ('django.db.models.fields.EmailField', [], {'unique': 'True', 'max_length': '254'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'primary': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'emails'", 'to': "orm['accounts.User']", 'on_delete': 'models.DO_NOTHING'}),
            'verified': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        'accounts.gpgkey': {
            'Meta': {'object_name': 'GPGKey'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'key_id': ('warehouse.utils.db_fields.CaseInsensitiveCharField', [], {'unique': 'True', 'max_length': '16'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'gpg_keys'", 'to': "orm['accounts.User']", 'on_delete': 'models.DO_NOTHING'})
        },
        'accounts.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'blank': 'True', 'symmetrical': 'False'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'name': ('django.db.models.fields.CharField', [], {'blank': 'True', 'max_length': '100'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'user_set'", 'blank': 'True', 'to': "orm['auth.Permission']", 'symmetrical': 'False'}),
            'username': ('warehouse.utils.db_fields.CaseInsensitiveCharField', [], {'unique': 'True', 'max_length': '50'})
        },
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['auth.Permission']", 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')", 'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'contenttypes.contenttype': {
            'Meta': {'db_table': "'django_content_type'", 'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType'},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        }
    }

    complete_apps = ['accounts']
