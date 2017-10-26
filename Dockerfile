# First things first, we build an image which is where we're going to compile
# our static assets with. It is important that the steps in this remain the
# same as the steps in Dockerfile.static, EXCEPT this may include additional
# steps appended onto the end.
FROM node:6.11.1 as static

WORKDIR /app/

# The list of C packages we need are almost never going to change, so installing
# them first, right off the bat lets us cache that and having node.js level
# dependency changes not trigger a reinstall.
RUN set -x \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        libjpeg62 \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# However, we do want to trigger a reinstall of our node.js dependencies anytime
# our package.json changes, so we'll ensure that we're copying that into our
# static container prior to actually installing the npm dependencies.
COPY package.json .babelrc /app/

# Installing npm dependencies is done as a distinct step and *prior* to copying
# over our static files so that, you guessed it, we don't invalidate the cache
# of installed dependencies just because files have been modified.
RUN set -x \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        libjpeg-dev \
    && npm install -g gulp-cli \
    && npm install \
    && apt-get remove --purge -y libjpeg-dev \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Actually copy over our static files, we only copy over the static files to
# save a small amount of space in our image and because we don't need them. We
# copy Gulpfile.babel.js last even though it's least likely to change, because
# it's very small so copying it needlessly isn't a big deal but it will save a
# small amount of copying when only Gulpfile.babel.js is modified.
COPY warehouse/static/ /app/warehouse/static/
COPY Gulpfile.babel.js /app/

RUN gulp dist

# Now we're going to build our actual application, but not the actual production
# image that it gets deployed into.
FROM python:3.6.3-stretch as build

# Define whether we're building a production or a development image. This will
# generally be used to control whether or not we install our development and
# test dependencies.
ARG DEVEL=no

# Install System level Warehouse build requirements, this is done before
# everything else because these are rarely ever going to change.
RUN set -x \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential libffi-dev libxml2-dev libxslt-dev libpq-dev \
        $(if [ "$DEVEL" = "yes" ]; then echo 'libjpeg-dev'; fi)

# We need a way for the build system to pass in a repository that will be used
# to install our theme from. For this we'll add the THEME_REPO build argument
# which takes a PEP 503 compatible repository URL that must be available to
# install the requirements/theme.txt requirement file.
ARG THEME_REPO

# We copy this into the docker container prior to copying in the rest of our
# application so that we can skip installing requirements if the only thing
# that has changed is the Warehouse code itself.
COPY requirements /tmp/requirements

# Install our development dependencies if we're building a development install
# otherwise this will do nothing.
RUN set -x \
    && if [ "$DEVEL" = "yes" ]; then pip --no-cache-dir --disable-pip-version-check install -r /tmp/requirements/dev.txt; fi



# Install the Python level Warehouse requirements, this is done after copying
# the requirements but prior to copying Warehouse itself into the container so
# that code changes don't require triggering an entire install of all of
# Warehouse's dependencies.
RUN set -x \
    && PIP_EXTRA_INDEX_URL=$THEME_REPO \
        pip --no-cache-dir --disable-pip-version-check \
            install -r /tmp/requirements/deploy.txt \
                    -r /tmp/requirements/main.txt \
                    $(if [ "$DEVEL" = "yes" ]; then echo '-r /tmp/requirements/tests.txt'; fi) \
                    $(if [ "$THEME_REPO" != "" ]; then echo '-r /tmp/requirements/theme.txt'; fi) \
    && find /usr/local -name '*.pyc' -delete

# Now we're going to build our actual application image, which will eventually
# pull in the static files that were built above.
FROM python:3.6.3-stretch

# Setup some basic environment variables that are ~never going to change.
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app/

# Define whether we're building a production or a development image. This will
# generally be used to control whether or not we install our development and
# test dependencies.
ARG DEVEL=no

# Install System level Warehouse requirements, this is done before everything
# else because these are rarely ever going to change.
RUN set -x \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        libpq5 libxml2 libxslt1.1  \
        $(if [ "$DEVEL" = "yes" ]; then echo 'bash libjpeg62 postgresql-client'; fi) \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy the directory into the container, this is done last so that changes to
# Warehouse itself require the least amount of layers being invalidated from
# the cache. This is most important in development, but it also useful for
# deploying new code changes.
COPY --from=static /app/warehouse/static/dist/ /app/warehouse/static/dist/
COPY --from=build /usr/local/ /usr/local/
COPY . /app/
