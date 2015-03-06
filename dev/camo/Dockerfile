FROM node:slim

# Install Camo dependencies
RUN set -x \
    && apt-get update \
    && apt-get install ca-certificates --no-install-recommends -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Camo
RUN set -x \
    && apt-get update \
    && apt-get install git --no-install-recommends -y \
    && git clone https://github.com/atmos/camo.git /camo \
    && apt-get purge git -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /camo/
