FROM python:3.4-slim

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/

# Install Warehouse's Dependencies
RUN set -x \
    && apt-get update \
    && apt-get install libpq5 libffi6 postgresql-client --no-install-recommends -y \
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
    && apt-get install gcc libpq-dev libffi-dev --no-install-recommends -y \
    && pip install -U pip setuptools \
    && pip install pyinotify \
    && pip install -c requirements.txt -r requirements-dev.txt -e . \
    && pip install -U https://github.com/dstufft/pyramid/archive/route-found.zip#egg=pyramid \
    && find /usr/local -type f -name '*.pyc' -name '*.pyo' -delete \
    && rm -rf ~/.cache/ \
    && apt-get purge gcc libpq-dev libffi-dev -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
