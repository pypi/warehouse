from django.db.models.signals import pre_syncdb

from warehouse.utils.db_fields import install_citext


# Registered in warehouse.management so that it is picked up during syncdb
pre_syncdb.connect(install_citext)
