# Set variables reused in Dockerfile
ARG PYTHON_IMAGE_VERSION=3.13.13-slim-bookworm

# First things first, we build an image which is where we're going to compile
# our static assets with. We use this stage in development. Node base is kept
# because some dependencies (sharp, sass-embedded) need node-gyp / native
# modules built against Node's headers; bun is just dropped in for the
# install + run steps which it does substantially faster than npm.
FROM node:25.8.1-bookworm AS static-deps

# Pull in bun for fast installs (bun install --frozen-lockfile reads bun.lock).
COPY --from=oven/bun:1.3.9 /usr/local/bin/bun /usr/local/bin/bun

WORKDIR /opt/warehouse/src/

# Trigger a reinstall whenever package.json or bun.lock changes.
COPY package.json bun.lock babel.config.js /opt/warehouse/src/

# Installing the JS dependencies is done as a distinct step and *prior* to
# copying over our static files so we don't invalidate this layer just
# because source files changed.
RUN --mount=type=cache,target=/root/.bun/install/cache,sharing=locked \
    bun install --frozen-lockfile




# This is our actual build stage, where we'll compile our static assets.
FROM static-deps AS static

# Actually copy over our static files, we only copy over the static files to
# save a small amount of space in our image and because we don't need them. We
# copy `rspack.config.js` last even though it's least likely to change, because
# it's very small so copying it needlessly isn't a big deal but it will save a
# small amount of copying when only `rspack.config.js` is modified.
COPY warehouse/static/ /opt/warehouse/src/warehouse/static/
COPY warehouse/admin/static/ /opt/warehouse/src/warehouse/admin/static/
COPY warehouse/locale/ /opt/warehouse/src/warehouse/locale/
COPY rspack.config.js /opt/warehouse/src/
COPY rspack.plugin.localize.js /opt/warehouse/src/
COPY rspack.plugin.manifest.js /opt/warehouse/src/
COPY bin/post-build.mjs /opt/warehouse/src/bin/

RUN NODE_ENV=production bun run build \
    && bun bin/post-build.mjs




# We'll build a light-weight layer along the way with just docs stuff
FROM python:${PYTHON_IMAGE_VERSION} AS docs

# Pull the uv binary in so we can use it as a faster pip / pip-compile.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/

# By default, Docker has special steps to avoid keeping APT caches in the layers, which
# is good, but in our case, we're going to mount a special cache volume (kept between
# builds), so we WANT the cache to persist.
RUN set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache;

# Install System level build requirements, this is done before everything else
# because these are rarely ever going to change.
# Usages:
#  - build-essential: make
#  - git: mkdocs plugin uses this for created/updated
#  - libcairo2: mkdocs uses cairosvg
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -x \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
       build-essential \
       git \
       libcairo2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# We create an /opt directory with a virtual environment in it to store our
# application in. uv picks this up via VIRTUAL_ENV below.
RUN set -x \
    && python3 -m venv /opt/warehouse

# Point uv (and shells) at the venv we just created.
# Hynek-recommended uv tuning (see https://hynek.me/articles/docker-uv/):
#   UV_LINK_MODE=copy        — silence hardlink-across-FS warnings (cache mount)
#   UV_COMPILE_BYTECODE=1    — pay the compile cost once, at build time
#   UV_PYTHON_DOWNLOADS=never — never auto-fetch a Python; use the system one
#   UV_PYTHON                — pin uv to the venv's interpreter
ENV VIRTUAL_ENV="/opt/warehouse" \
    UV_PROJECT_ENVIRONMENT="/opt/warehouse" \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON="/opt/warehouse/bin/python"
ENV PATH="/opt/warehouse/bin:${PATH}"

# Install Python deps via uv sync from pyproject.toml + uv.lock.
# Bind-mount the lock + manifest so they don't enter the layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    set -x \
    && uv sync --frozen --no-default-groups \
            --group docs-dev --group docs-user --group docs-blog \
    && uv pip check

WORKDIR /opt/warehouse/src/

# We'll make the docs container run as a non-root user, ensure that the built
# documentation belongs to the same user on the host machine.
ARG USER_ID
ARG GROUP_ID
RUN groupadd -o -g $GROUP_ID -r docs
RUN useradd -o -m -u $USER_ID -g $GROUP_ID docs
RUN chown docs /opt/warehouse/src
USER docs




# Now we're going to build our actual application, but not the actual production
# image that it gets deployed into.
FROM python:${PYTHON_IMAGE_VERSION} AS build

# Pull the uv binary in so we can use it as a faster pip / pip-compile.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/

# Define whether we're building a production or a development image. This will
# generally be used to control whether or not we install our development and
# test dependencies.
ARG DEVEL=no

# Define whether we're building a CI image. This will include all the docs stuff
# as well for the matrix!
ARG CI=no

# To enable Ipython in the development environment set to yes (for using ipython
# as the warehouse shell interpreter,
# i.e. 'docker compose run --rm web python -m warehouse shell --type=ipython')
ARG IPYTHON=no

# We create an /opt directory with a virtual environment in it to store our
# application in. uv picks this up via VIRTUAL_ENV below.
RUN set -x \
    && python3 -m venv /opt/warehouse

# Point uv (and shells) at the venv we just created.
# See the docs stage above for the rationale behind each UV_* variable.
ENV VIRTUAL_ENV="/opt/warehouse" \
    UV_PROJECT_ENVIRONMENT="/opt/warehouse" \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON="/opt/warehouse/bin/python"
ENV PATH="/opt/warehouse/bin:${PATH}"

# Install Python deps via uv sync from pyproject.toml + uv.lock.
# [project].dependencies (was main.in) is always installed; additional groups
# are conditionally pulled in based on build args.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    set -x \
    && uv sync --frozen --no-default-groups \
            --group deploy \
            $(if [ "$DEVEL" = "yes" ]; then echo '--group dev --group tests --group lint'; fi) \
            $(if [ "$DEVEL" = "yes" ] && [ "$IPYTHON" = "yes" ]; then echo '--group ipython'; fi) \
            $(if [ "$CI" = "yes" ]; then echo '--group docs-dev --group docs-user --group docs-blog'; fi) \
    && uv pip check




# Now we're going to build our actual application image, which will eventually
# pull in the static files that were built above.
FROM python:${PYTHON_IMAGE_VERSION}

# Pull the uv binary in so it is available at runtime. Used by bin/lint
# (uv lock --check), make deps_upgrade_*, and any in-container shell work.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/

# Setup some basic environment variables that are ~never going to change.
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /opt/warehouse/src/
ENV PATH="/opt/warehouse/bin:${PATH}"

WORKDIR /opt/warehouse/src/

# Define whether we're building a production or a development image. This will
# generally be used to control whether or not we install our development and
# test dependencies.
ARG DEVEL=no

# Define whether we're building a CI image. This will include all the docs stuff
# as well for the matrix!
ARG CI=no

# By default, Docker has special steps to avoid keeping APT caches in the layers, which
# is good, but in our case, we're going to mount a special cache volume (kept between
# builds), so we WANT the cache to persist.
RUN set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache;

# Install System level Warehouse requirements, this is done before everything
# else because these are rarely ever going to change.
# Usages:
#  - build-essential: make
#  - postgresql-client: make initdb and friends
#  - oathtool: make totp
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -x \
    && if [ "$DEVEL" = "yes" ]; then \
        apt-get update \
        && apt-get install --no-install-recommends -y \
           build-essential \
           postgresql-client \
           oathtool \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*; \
    fi

# Copy the directory into the container, this is done last so that changes to
# Warehouse itself require the least amount of layers being invalidated from
# the cache. This is most important in development, but it also useful for
# deploying new code changes.
COPY --from=static /opt/warehouse/src/warehouse/static/dist/ /opt/warehouse/src/warehouse/static/dist/
COPY --from=static /opt/warehouse/src/warehouse/admin/static/dist/ /opt/warehouse/src/warehouse/admin/static/dist/
COPY --from=build /opt/warehouse/ /opt/warehouse/
COPY . /opt/warehouse/src/

# Pre-cache TLD list
RUN tldextract --update
# Load our module to pre-compile as much bytecode as we can easily.
# Saves time collectively on container boot!
RUN python -m warehouse db -h
