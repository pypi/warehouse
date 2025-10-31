# Documentation

## Developer documentation

The developer documentation is hosted at [warehouse.pypa.io](https://warehouse.pypa.io). It's written in
[reStructuredText](https://docutils.sourceforge.io/rst.html) or [Markdown](https://www.markdownguide.org/) (via [MyST](https://myst-parser.readthedocs.io/en/latest/)) and built using
[Sphinx](https://www.sphinx-doc.org/).

### Layout

The developer documentation is located in the `docs/dev` directory.

### Local development

To run a single local build of the dev docs, you can use the `dev-docs`
Makefile target:

```shell
make dev-docs
```

That will produce a local build under `docs/dev/_build/`.

To run a local development server, you can use `docker compose`:

```shell
docker compose up dev-docs
```

Once running, you can visit a local build of the pages at [localhost:10002](http://localhost:10002).

## User documentation

The user documentation is hosted at [docs.pypi.org](https://docs.pypi.org). It's written in
[Markdown](https://www.markdownguide.org/) and built using [MkDocs](https://www.mkdocs.org/).

### Layout

The user documentation is located in the `docs/user` directory.

### Local development

To run a single local build of the user docs, you can use the `user-docs`
Makefile target:

```shell
make user-docs
```

That will produce a local build under `docs/user-site/`.

To run a local development server, you can use `docker compose`:

```shell
docker compose up user-docs
```

Once running, you can visit a local build of the user documentation at [localhost:10000](http://localhost:10000).

## PyPI blog

The PyPI blog is hosted at [blog.pypi.org](https://blog.pypi.org). Like the user documentation,
it's written in [Markdown](https://www.markdownguide.org/) and built using [MkDocs](https://www.mkdocs.org/).

### Layout

The blog is located in the `docs/blog` directory.

### Local development

To run a single local build of the blog, you can use the `blog`
Makefile target:

```shell
make blog
```

That will produce a local build under `docs/blog-site/`.

To run a local development server, you can use `docker compose`:

```shell
docker compose up blog
```

Once running, you can visit a local build of the blog at [localhost:10001](http://localhost:10001).
