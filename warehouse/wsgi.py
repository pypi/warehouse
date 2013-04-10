from configurations import importer
from django.core.wsgi import get_wsgi_application

# Install the Configurations importer
importer.install()

# Create the WSGI application
application = get_wsgi_application()
