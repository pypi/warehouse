FROM python:3.5.0-slim

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

# Uncomment the below line and add the appropriate private index for the
# pypi-theme package.
# ENV PIP_EXTRA_INDEX_URL ...

# Install Warehouse
RUN set -x \
    && apt-get update \
    && apt-get install gcc libpq-dev libffi-dev --no-install-recommends -y \
    && pip install -U pip setuptools \
    && pip install -r requirements/main.txt -r requirements/dev.txt \
                   -r requirements/tests.txt \
    # Uncomment the below line if you're working on the PyPI theme, this is a
    # private repository due to the fact that other people's IP is contained
    # in it.
    # && pip install -c requirements/main.txt -r requirements/deploy.txt \
    && find /usr/local -type f -name '*.pyc' -name '*.pyo' -delete \
    && rm -rf ~/.cache/ \
    && apt-get purge gcc libpq-dev libffi-dev -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
