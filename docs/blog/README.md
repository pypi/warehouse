# PyPI Blog

This blog is hosted at <https://blog.pypi.org/> to provide a way for the PyPI
Administrators to share new features, breaking changes, and curiosities with
the community.

Posts are written in [Markdown](https://www.markdownguide.org) and built using
[mkdocs](https://www.mkdocs.org).

The blog is built and deployed with [readthedocs.org](https://readthedocs.org/projects/blogpypiorg/).

See our [`.readthedocs.yml`](../.readthedocs.yml) for configuration.

## Setup

After following the [installation instructions](https://warehouse.pypa.io/development/getting-started.html#detailed-installation-instructions)
all the remaining commands take place in containers.

The project can be previewed by running `docker compose up blog` from the
base directory of your clone of `pypa/warehouse`. This will start a `mkdocs`
development server that will live reload as you change the contents of this
directory, including the `docs/mkdocs-blog.yml` configuration.

Open <http://localhost:10001/> to view the blog.

## Building

You may also build the static blog files by running `make blog` from the base
directory of your clone of `pypa/warehouse`. This will build the static files
into the `docs/blog-site/` directory.
