# Documentation

## Developer documentation

The developer documentation is hosted at [warehouse.pypa.io](https://warehouse.pypa.io). It's written in
[Markdown](https://www.markdownguide.org/) and built using [Zensical](https://zensical.org/).

### Layout

The developer documentation is located in the `docs/dev` directory.

### Local development

To run a single local build of the dev docs, you can use the `dev-docs`
Makefile target:

```shell
make dev-docs
```

That will produce a local build under `docs/dev-site/`.

To run a local development server, you can use `docker compose`:

```shell
docker compose up dev-docs
```

Once running, you can visit a local build of the pages at [localhost:10002](http://localhost:10002).

## User documentation

The user documentation is hosted at [docs.pypi.org](https://docs.pypi.org). It's written in
[Markdown](https://www.markdownguide.org/) and built using [Zensical](https://zensical.org/).

### Layout

The user documentation is located in the `docs/user` directory. Theme partials that
override the built-in ones live outside `docs/user`, in `docs/user-overrides`.

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

The PyPI blog is hosted at [blog.pypi.org](https://blog.pypi.org). It's written in
[Markdown](https://www.markdownguide.org/) and built using [MkDocs](https://www.mkdocs.org/)
with [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/). The developer and
user documentation have moved to [Zensical](https://zensical.org/); the blog has not, because
Zensical does not yet implement the plugins it depends on — see
[Migrating the blog to Zensical](#migrating-the-blog-to-zensical) below.

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

### Migrating the blog to Zensical

Material for MkDocs entered maintenance mode in November 2025, so the blog needs to move
to Zensical eventually. It cannot move yet: the blog build depends on four plugins that
Zensical has committed to but has not yet implemented. Zensical ignores unknown plugins
silently and still exits `0`, so the build looks green while the site loses its post
index, feeds, tag pages, and social cards.

The gating issues on the [Zensical backlog](https://github.com/zensical/backlog):

| Plugin                     | Backlog issue                                             | What breaks without it                             |
| -------------------------- | --------------------------------------------------------- | -------------------------------------------------- |
| `material/blog`            | [#30](https://github.com/zensical/backlog/issues/30)      | Post index, pagination, archives, author profiles  |
| `mkdocs-rss-plugin`        | [#27](https://github.com/zensical/backlog/issues/27)      | `feed_rss_created.xml` and the JSON feeds          |
| `material/social`          | [#37](https://github.com/zensical/backlog/issues/37)      | Social cards (`og:image`)                          |
| `material/tags`            | [#38](https://github.com/zensical/backlog/issues/38)      | Tag pages                                          |

`material-plausible-plugin` is not on the backlog at all. The user documentation replaced
it with a four-line theme partial in `docs/user-overrides`; the blog can do the same when
it migrates.

Once those four issues close, migrating the blog means pointing `bin/rtd-docs`,
`docker-compose.yml`, and the `blog` Makefile target at `zensical build`, replacing
`requirements/docs-blog.in` with `zensical`, and adding a `site_url`-backed sitemap check
to the review. Verify the published post URLs still resolve — the current config pins them
with `post_url_format` and `pagination_url_format` to stay compatible with Read the Docs
redirects.
