# syntax=docker/dockerfile:1

# First things first, we build an image which is where we're going to compile
# our static assets with. We use this stage in development.
FROM node:26.4.0-trixie AS static-deps

# Set our working directory to our src directory
WORKDIR /opt/warehouse/src/

# However, we do want to trigger a reinstall of our node.js dependencies anytime
# our package.json changes, so we'll ensure that we're copying that into our
# static container prior to actually installing the npm dependencies.
COPY package.json package-lock.json babel.config.js /opt/warehouse/src/

# Installing npm dependencies is done as a distinct step and *prior* to copying
# over our static files so that, you guessed it, we don't invalidate the cache
# of installed dependencies just because files have been modified.
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci




# This is our actual build stage, where we'll compile our static assets.
FROM static-deps AS static

# Actually copy over our static files, we only copy over the static files to
# save a small amount of space in our image and because we don't need them. We
# copy `webpack.config.js` last even though it's least likely to change, because
# it's very small so copying it needlessly isn't a big deal but it will save a
# small amount of copying when only `webpack.config.js` is modified.
COPY warehouse/static/ /opt/warehouse/src/warehouse/static/
COPY warehouse/admin/static/ /opt/warehouse/src/warehouse/admin/static/
COPY warehouse/locale/ /opt/warehouse/src/warehouse/locale/
COPY webpack.config.js /opt/warehouse/src/
COPY webpack.plugin.localize.js /opt/warehouse/src/

RUN NODE_ENV=production npm run build




# Create a base image that contains some helpers and settings for our python
# stages to inherit from.
FROM python:3.14.6-slim-trixie AS base

# Copy our helpers over into the base image
COPY bin/docker/* /usr/local/bin/

# By default, Docker has special steps to avoid keeping APT caches in the layers, which
# is good, but in our case, we're going to mount a special cache volume (kept between
# builds), so we WANT the cache to persist.
RUN set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# Pre-compile the stdlib bytecode to save time collectively on container boot!
RUN python -m compileall /usr/local/lib -j 0

# Set our working directory to our src directory
WORKDIR /opt/warehouse/src/

# Setup our $PATH so that it contains what will be our normal bin directory.
ENV PATH="/opt/warehouse/bin:${PATH}"




# We'll build a light-weight layer along the way with just docs stuff
FROM base AS docs

# Install System level build requirements, this is done before everything else
# because these are rarely ever going to change.
# Usages:
#  - build-essential: make
#  - git: mkdocs plugin uses this for created/updated
#  - libcairo2: mkdocs uses cairosvg
RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
        apt-install \
            build-essential \
            git \
            libcairo2

# We create an /opt directory with a virtual environment in it to store our
# application in, we'll use --upgrade-deps to make sure we have the latest
# version of pip.
RUN --mount=type=cache,id=pkg,target=/root/.cache \
        create-venv /opt/warehouse

# Install the Python level Warehouse requirements, this is done after copying
# the requirements but prior to copying Warehouse itself into the container so
# that code changes don't require triggering an entire install of all of
# Warehouse's dependencies.
RUN --mount=type=cache,id=pkg,target=/root/.cache \
    --mount=type=bind,src=requirements/,dst=/opt/warehouse/src/requirements/ \
    pip-install \
        -r requirements/docs-dev.txt \
        -r requirements/docs-user.txt \
        -r requirements/docs-blog.txt

# We'll make the docs container run as a non-root user, ensure that the built
# documentation belongs to the same user on the host machine.
ARG USER_ID
ARG GROUP_ID
RUN groupadd -o -g $GROUP_ID -r docs
RUN useradd -o -m -u $USER_ID -g $GROUP_ID docs
RUN chown docs /opt/warehouse/src
USER docs




# Now we're going to build our actual application image
FROM base

# Setup some basic environment variables that are ~never going to change.
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/opt/warehouse/src/

# We create an /opt directory with a virtual environment in it to store our
# application in
RUN --mount=type=cache,id=pkg,target=/root/.cache \
        create-venv /opt/warehouse

# Define whether we're building a production or a development image. This will
# generally be used to control whether or not we install our development and
# test dependencies.
ARG DEVEL=no

# Install System level Warehouse requirements, this is done before everything
# else because these are rarely ever going to change.
# Usages:
#  - build-essential: make
#  - postgresql-client: make initdb and friends
#  - oathtool: make totp
RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    set -x \
    && if [ "$DEVEL" = "yes" ]; then \
        apt-install \
           build-essential \
           postgresql-client \
           oathtool \
           fd-find \
        # Debian renames the `fd` binary to `fdfind`, so we'll rename it back to `fd`.
        && ln -s $(which fdfind) /usr/local/bin/fd; \
    fi

# Define whether we're building a CI image. This will include all the docs stuff
# as well for the matrix!
ARG CI=no

# Install the Python level Warehouse requirements, this is done after copying
# the requirements but prior to copying Warehouse itself into the container so
# that code changes don't require triggering an entire install of all of
# Warehouse's dependencies.
RUN --mount=type=cache,id=pkg,target=/root/.cache \
    --mount=type=bind,src=requirements/,dst=/opt/warehouse/src/requirements/ \
    pip-install \
        -r requirements/deploy.txt \
        -r requirements/main.txt \
        $(if [ "$DEVEL" = "yes" ]; then echo '-r requirements/dev.txt -r requirements/tests.txt -r requirements/lint.txt'; fi) \
        $(if [ "$CI" = "yes" ]; then echo '-r requirements/docs-dev.txt -r requirements/docs-user.txt -r requirements/docs-blog.txt'; fi )

# To enable Ipython in the development environment set to yes (for using ipython
# as the warehouse shell interpreter,
# i.e. 'docker compose run --rm web python -m warehouse shell --type=ipython')
ARG IPYTHON=no

# Install the IPython dependencies, which has to be done as it's own step because
# we don't have pinned hashes for IPython.
RUN --mount=type=cache,id=pkg,target=/root/.cache \
    --mount=type=bind,src=requirements/,dst=/opt/warehouse/src/requirements/ \
    if [ "$DEVEL" = "yes" ] && [ "$IPYTHON" = "yes" ]; then \
      pip-install -r requirements/ipython.txt; \
    fi

# Pre-compile our dependencies bytecode to save time collectively on container boot!
RUN python -m compileall /opt/warehouse/lib/ -j 0

# Copy our compiled static files. These should overlay cleanly on top of the
# virtual environment and even when that gets invalidated, copything these is
# super fast.
COPY --from=static /opt/warehouse/src/warehouse/static/dist/ /opt/warehouse/src/warehouse/static/dist/
COPY --from=static /opt/warehouse/src/warehouse/admin/static/dist/ /opt/warehouse/src/warehouse/admin/static/dist/

# Copy warehouse into the container, this is done last so that changes to
# Warehouse itself require the least amount of layers being invalidated from
# the cache. This is most important in development, but it also useful for
# deploying new code changes.
#
# NOTE: We copy bin/release on it's own so that we can still exclude the rest
#       of the bin/ directory when we copy over everything else.
COPY bin/release /opt/warehouse/src/bin/release
COPY --exclude=requirements \
     --exclude=bin \
     --exclude=docs \
     --exclude=babel.config.js \
     --exclude=eslint.config.mjs \
     --exclude=package-lock.json \
     --exclude=package.json \
     --exclude=webpack.config.js \
     --exclude=webpack.plugin.localize.js \
        . /opt/warehouse/src/


# Pre-compile our module's bytecode to save time collectively on container boot!
# NOTE: We only do this when we're not building a dev build, because a dev build
#       will likely have a checkout mounted over warehouse anyways, so these
#       *.pyc files won't be used in that case.
RUN if [ "$DEVEL" != "yes" ]; then python -m compileall warehouse/ -j 0; fi

# Pre-cache TLD list
# NOTE: We only do this when we're not building a dev build, because a dev build
#       doesn't need to keep an updated tldextract database an can fall back to
#       snapshot included in tldextract.
RUN if [ "$DEVEL" != "yes" ]; then tldextract --update; fi
