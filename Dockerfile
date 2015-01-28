# --------------------------------------------------------------------------
# This is a Dockerfile to build an Ubuntu 14.04 Docker image with
# Warehouse
#
# Use a command like:
#     docker build -t <user>/warehouse .
# --------------------------------------------------------------------------

FROM  orchardup/python:3.4
MAINTAINER  Marc Abramowitz <marc@marc-abramowitz.com> (@msabramo)

ENV DEBIAN_FRONTEND noninteractive
ENV LC_ALL C

RUN apt-get update && apt-get install -y software-properties-common && add-apt-repository ppa:chris-lea/node.js
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libffi-dev \
    libpq-dev \
    libyaml-dev \
    nodejs \
    openjdk-7-jre-headless \
    postgresql \
    postgresql-contrib \
    redis-server \
    ruby \
    ruby-dev \
    tree \
    vim-nox \
    wget
RUN wget --no-verbose https://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-1.4.2.deb
RUN dpkg -i elasticsearch-1.4.2.deb
RUN gem install compass
RUN npm install -g grunt-cli
RUN wget --no-verbose https://bootstrap.pypa.io/get-pip.py
RUN python3 get-pip.py
ADD . warehouse
WORKDIR warehouse
RUN pip install -r dev-requirements.txt
RUN pip install \
    honcho \
    httpie \
    ipython \
    ptpython
RUN /etc/init.d/postgresql start && \
    sudo -u postgres createuser --superuser root && \
    sudo -u postgres createdb warehouse && \
    sudo -u postgres psql warehouse -c 'CREATE EXTENSION IF NOT EXISTS citext' && \
    sudo -u postgres psql warehouse -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' && \
    warehouse -c dev/config.yml migrate upgrade head
# RUN /etc/init.d/elasticsearch start && \
#     /etc/init.d/postgresql start && \
#     sleep 5 && \
#     warehouse -c dev/config.yml search reindex

EXPOSE 5432 6379 9000 9200

CMD ["honcho", "start"]
