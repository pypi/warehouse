FROM python:3.5.2-slim

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/
# Setup proxy configuration
# ENV http_proxy "http://proxy.foo.com:1234"
# ENV https_proxy "http://proxy.foo.com:1234"
# ENV no_proxy "*.foo.com"

# Setup the locales in the Dockerfile
RUN set -x \
    && apt-get update \
    && apt-get install locales -y \
    && locale-gen en_US.UTF-8

# Install Warehouse's Dependencies
RUN set -x \
    && apt-get update \
    && apt-get install curl -y \
    && curl -sL https://deb.nodesource.com/setup_5.x | bash - \
    && apt-get install git libpq5 libjpeg62 libffi6 libfontconfig postgresql-client --no-install-recommends nodejs -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN set -x \
    && apt-get update \
    && apt-get install inotify-tools wget bzip2 gcc g++ make libpq-dev libjpeg-dev libffi-dev --no-install-recommends -y \
    && wget https://saucelabs.com/downloads/sc-4.3.14-linux.tar.gz -O /tmp/sc.tar.gz \
    && tar zxvf /tmp/sc.tar.gz --strip 1 -C /usr/ \
    && chmod 755 /usr/bin/sc

COPY package.json /tmp/package.json

# Install NPM dependencies
RUN set -x \
    && npm install -g phantomjs-prebuilt gulp-cli \
    && cd /tmp \
    && npm install \
    && mkdir /app \
    && cp -a /tmp/node_modules /app/

COPY requirements /tmp/requirements

# Install Python dependencies
RUN set -x \
    && pip install -U pip setuptools \
    && pip install -r /tmp/requirements/dev.txt \
                   -r /tmp/requirements/tests.txt \
    && pip install -r /tmp/requirements/deploy.txt \
                   -r /tmp/requirements/main.txt \
    # Uncomment the below line if you're working on the PyPI theme, this is a
    # private repository due to the fact that other people's IP is contained
    # in it.
    # && pip install -c requirements/main.txt -r requirements/theme.txt \
    && find /usr/local -type f -name '*.pyc' -name '*.pyo' -delete \
    && rm -rf ~/.cache/

# Copy the directory into the container
COPY . /app/

# Set our work directory to our app directory
WORKDIR /app/

# Uncomment the below line and add the appropriate private index for the
# pypi-theme package.
# ENV PIP_EXTRA_INDEX_URL ...
