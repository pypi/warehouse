FROM python:3.4-slim

# Install Warehouse's Dependencies
RUN set -x \
    && apt-get update \
    && apt-get install libpq5 postgresql-client --no-install-recommends -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy the directory into the Dockerfile
COPY . /app/

# Set our work directory to our app directory
WORKDIR /app/

# Install Warehouse
RUN set -x \
    && apt-get update \
    && apt-get install gcc libpq-dev --no-install-recommends -y \
    && pip install -r dev/requirements.txt \
    && find /usr/local -type f -name '*.pyc' -name '*.pyo' -delete \
    && rm -rf ~/.cache/ \
    && apt-get purge gcc libpq-dev -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
