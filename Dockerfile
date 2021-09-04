# ---------------------------------- STATIC ----------------------------------

# First things first, we build an image which is where we're going to compile
# our static assets with.
FROM node:14.4.0 as static

WORKDIR /opt/warehouse/src/

# By default, Docker has special steps to avoid keeping APT caches in the layers, which
# is good, but in our case, we're going to mount a special cache volume (kept between
# builds), so we WANT the cache to persist.
RUN set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache;

# The list of C packages we need are almost never going to change, so installing
# them first, right off the bat lets us cache that and having node.js level
# dependency changes not trigger a reinstall.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    apt-get update; \
    apt-get install --no-install-recommends -y \
        libjpeg-dev \
        nasm

# However, we do want to trigger a reinstall of our node.js dependencies anytime
# our package.json changes, so we'll ensure that we're copying that into our
# static container prior to actually installing the npm dependencies.
COPY package.json package-lock.json .babelrc /opt/warehouse/src/

# Installing npm dependencies is done as a distinct step and *prior* to copying
# over our static files so that, you guessed it, we don't invalidate the cache
# of installed dependencies just because files have been modified.
RUN set -eux \
    npm install -g npm@latest; \
    npm install -g gulp-cli; \
    npm ci;

# Actually copy over our static files, we only copy over the static files to
# save a small amount of space in our image and because we don't need them. We
# copy Gulpfile.babel.js last even though it's least likely to change, because
# it's very small so copying it needlessly isn't a big deal but it will save a
# small amount of copying when only Gulpfile.babel.js is modified.
COPY warehouse/static/ /opt/warehouse/src/warehouse/static/
COPY warehouse/admin/static/ /opt/warehouse/src/warehouse/admin/static/
COPY Gulpfile.babel.js /opt/warehouse/src/

RUN gulp dist


# ---------------------------------- BASE -----------------------------------
FROM python:3.8.2-slim-buster as base

# Setup some basic environment variables that are ~never going to change.
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /opt/warehouse/src/
ENV PATH="/opt/warehouse/bin:${PATH}"

WORKDIR /opt/warehouse/src/

# By default, Docker has special steps to avoid keeping APT caches in the layers, which
# is good, but in our case, we're going to mount a special cache volume (kept between
# builds), so we WANT the cache to persist.
RUN set -eux \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# Install System level Warehouse requirements, this is done before everything
# else because these are rarely ever going to change.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    apt-get update; \
    apt-get install --no-install-recommends -y \
        libpq5 \
        libxml2 \
        libxslt1.1 \
        libcurl4 \
    ;

# ---------------------------------- BUILD ----------------------------------

# Now we're going to build our actual application, but not the actual production
# image that it gets deployed into.
FROM base as build

# Install System level Warehouse build requirements, this is done before
# everything else because these are rarely ever going to change.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    apt-get update; \
    apt-get install --no-install-recommends -y \
        build-essential \
        libcurl4-openssl-dev \
        libffi-dev \
        libpq-dev \
        libssl-dev \
        libxml2-dev \
        libxslt-dev \
    ;

# We create an /opt directory with a virtual environment in it to store our
# application in.
RUN python3 -m venv /opt/warehouse

# Pip configuration (https://github.com/pypa/warehouse/pull/4584)
ENV PIP_NO_BINARY=hiredis PIP_DISABLE_PIP_VERSION_CHECK=1

# We copy this into the docker container prior to copying in the rest of our
# application so that we can skip installing requirements if the only thing
# that has changed is the Warehouse code itself.
COPY requirements /tmp/requirements

# Next, we want to update pip, setuptools, and wheel inside of this virtual
# environment to ensure that we have the latest versions of them.
RUN --mount=type=cache,target=/root/.cache \
    pip install -r /tmp/requirements/pip.txt

# Install the Python level Warehouse requirements, this is done after copying
# the requirements but prior to copying Warehouse itself into the container so
# that code changes don't require triggering an entire install of all of
# Warehouse's dependencies.
RUN --mount=type=cache,target=/root/.cache \
    set -eux; \
    pip install -r /tmp/requirements/all-base.txt; \
    find /opt/warehouse -name '*.pyc' -delete;

# ---------------------------------- DEV ----------------------------------

FROM build as dev

# To enable Ipython in the development environment set to yes (for using ipython
# as the warehouse shell interpreter,
# i.e. 'docker-compose run --rm web python -m warehouse shell --type=ipython')
ARG IPYTHON=no

# This is a work around because otherwise postgresql-client bombs out trying
# to create symlinks to these directories.
RUN set -eux; \
    mkdir -p /usr/share/man/man1; \
    mkdir -p /usr/share/man/man7

# Install System level Warehouse build requirements, this is done before
# everything else because these are rarely ever going to change.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    apt-get update; \
    apt-get install --no-install-recommends -y \
        bash \
        libjpeg-dev \
        libjpeg62 \
        postgresql-client \
    ;

# Install our development dependencies
RUN set -eux; \
    pip install -r /tmp/requirements/dev.txt; \
    if [ "$IPYTHON" = "yes" ]; then pip install -r /tmp/requirements/all-ipython.txt; fi;

RUN pip install -r /tmp/requirements/all-lint-test.txt;


# ---------------------------------- APP ----------------------------------
FROM base as app
# Now we're going to build our actual application image, which will eventually
# pull in the static files that were built above.

# Copy the directory into the container, this is done last so that changes to
# Warehouse itself require the least amount of layers being invalidated from
# the cache. This is most important in development, but it also useful for
# deploying new code changes.
COPY --from=static /opt/warehouse/src/warehouse/static/dist/ /opt/warehouse/src/warehouse/static/dist/
COPY --from=static /opt/warehouse/src/warehouse/admin/static/dist/ /opt/warehouse/src/warehouse/admin/static/dist/
COPY --from=build /opt/warehouse/ /opt/warehouse/
COPY . /opt/warehouse/src/
