from django.db.models import fields
from south.modelsinspector import add_introspection_rules


class CaseInsensitiveCharField(fields.CharField):
    # NOTE: You MUST manually add a CHECK CONSTRAINT to the database for
    #           max_length to be respected in the DB.

    def db_type(self, connection):
        return "citext"


add_introspection_rules([],
    ["^warehouse\.utils\.db_fields\.CaseInsensitiveCharField"],
)
