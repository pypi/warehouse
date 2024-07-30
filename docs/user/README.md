# PyPI User Facing Documentation

This documentation is hosted at https://docs.pypi.org/ to provide
user-facing documentation for using PyPI.

Documentation is written in [Markdown](https://www.markdownguide.org) and built
using [mkdocs](https://www.mkdocs.org).

The documentation is built and deployed with [readthedocs.org](https://readthedocs.org/projects/docspypiorg/).

See our [`.readthedocs.yml`](../.readthedocs.yml) for configuration.

## Setup

After following the [installation instructions](https://warehouse.pypa.io/development/getting-started.html#detailed-installation-instructions)
all the remaining commands take place in containers.

The project can be previewed by running `docker compose up user-docs` from the
base directory of your clone of pypa/warehouse. This will start a `mkdocs`
development server that will live reload as you change the contents of this
directory, including the `mkdocs.yml` configuration.
