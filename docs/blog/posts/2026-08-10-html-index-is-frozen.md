---
title: The HTML representation of the index API is now frozen
description: >
  PyPI has adopted PEP 833, which "freezes" the HTML representation
  of the index API. New packages and releases will continue to
  appear in the HTML representation, but future standardization
  and development efforts will focus on the JSON representation.
authors:
  - woodruffw
date: 2026-08-10
tags:
  - apis
  - integrations
---

PyPI has adopted [PEP 833], which "freezes" the
[HTML representation] of the [index API], which is also
sometimes called the "simple API" or the "simple repository API."

New packages and releases will continue to appear in the HTML
representation, meaning this has **no breaking implications**
for downstream index consumers.

However, future standardization and development efforts will focus
on the JSON representation, and downstreams that consume only the HTML
representation are **strongly encouraged** to transition to the JSON
representation to ensure access to the latest and greatest index features.

[PEP 833]: https://peps.python.org/pep-0833/

[HTML representation]: https://packaging.python.org/en/latest/specifications/simple-repository-api/#html-serialization

[index API]: https://docs.pypi.org/api/index-api/

<!-- more -->

## Background

As the name suggests, PyPI's primary responsibility is serving a
_package index_. Installers (like pip and uv) consume this
index as part of resolving and installing dependencies.

For historical reasons, there are two different standard _representations_
of a Python packaging index:

- The HTML representation, which predates standardization, and was
  retroactively standardized with [PEP 503].

    The HTML index is _essentially_ a bare-bones version of the
    human-readable index that PyPI once served, back before PyPI
    was a resource that installers automatically retrieved packages
    from. It's that old!

- The JSON representation, which was standardized with [PEP 691].

    Unlike the HTML representation, the JSON representation was designed
    from the ground-up to be useful to machine clients, rather than
    humans.

The two representations are more or less[^moreorless] coextensive in terms of
serving the information that installers care about. This is intentional:
efforts to extend the simple index over the years have worked hard
to put that state into both representations.

Doing so with the HTML representation is often unwieldy, as
metadata that naturally fits JSON's object model needs to be
shoehorned into nooks and crannies (mainly HTML attributes and new `<meta>` tags)
that won't interfere with pre-existing assumptions about the
HTML's shape.

Unfortunately, that shoehorning process is has become harder over time:

- Many consumers have made suboptimal, unsound assumptions about
  the shape of shape of PyPI's HTML representation. More
  precisely: they go beyond assuming the basic shape of the HTML,
  and actually make assumptions about semantically irrelevant
  aspects like whitespace, attribute order, &amp;c.

    This makes even "shape preserving" changes to the HTML representation
    fraught.

    By contrast, consumers of the JSON representation don't generally
    encounter these issues. Some of that is probably a function of
    the JSON representation being newer, but a large part is
    likely because, unlike HTML, users don't find themselves open-coding
    a JSON parser in high-level languages.

- Because the fundamental shape of the HTML representation can't be changed,
  adding new pieces of metadata to it becomes an exercise in creative
  munging: things that are natural to express as object members in
  JSON need to be shoehorned into new, flat `<meta>` tags or HTML
  attributes in the HTML representation.

    [PEP 792] is a good example of this. Compare the JSON representation:

    ```json
    {
        "meta": {
            "api-version": "1.4"
        },
        "project-status": {
            "status": "quarantined",
            "reason": "the project is haunted"
        }
    }
    ```

    ...to the HTML one:

    ```html
    <meta name="pypi:repository-version" content="1.4">
    <meta name="pypi:project-status" content="quarantined">
    <meta name="pypi:project-status-reason" content="the project is haunted">
    ```

    This may not seem so bad in isolation, but keep in mind that this
    flattening and munging needs to happen for every single
    new addition to the index.

- Even when we _do_ successfully shoehorn features into the
  HTML representation (on paper, and on PyPI), it often
  **doesn't matter to users**: users are bifurcated between adoption
  of the JSON representation (which doesn't have these issues)
  and third-party (often private) indices that only
  implement the absolute bare minimum required in [PEP 503].

    As a result, even when we _do_ update the HTML representation,
    users rarely benefit from it.

[PEP 503]: https://peps.python.org/pep-0503/

[PEP 691]: https://peps.python.org/pep-0691/

[PEP 792]: https://peps.python.org/pep-0792/

"Freezing" the HTML representation is our way of acknowledging this
situation. It's our way of saying that we can't[^yet] deprecate the
HTML representation, but that we don't want to keep _extending_ it
given how lopsided the tradeoffs are.

## Do I have to do anything?

**No!**

The HTML representation is **not going away**, and will not
go "stale" in terms of *content* updates. "Freezing" means that
Python packaging as a whole has made a _policy_ decision
to not continue to munge features into its _structure_.

In other words: the HTML representation will continue to be served by PyPI
for the foreseeable future, but Python packaging as a whole
will no longer prioritize attempting to shoe-horn new pieces
of metadata into its relatively inflexible HTML structure.

The longer answers:

- If you're an "individual" downstream package consumer (e.g., a
  user who installs packages from PyPI through a tool like pip or uv):
  this will have **no impact on you**.

    This is for two reasons: first, nothing is actually changing about
    the HTML representation from your (your tool's) perspective.
    Second, your tool is _probably_ already preferring the JSON
    representation: pip has supported the JSON representation since
    [22.2], and uv has always supported it.

- If you're a "bulk" index consumer (e.g., someone who mirrors
  all of PyPI into a public or private) copy: you *also* won't
  be affected by this.

    However, we **strongly recommend** that you consider switching
    to the JSON representation as your primary consumption format:
    you can still serve the HTML representation in your mirror
    by reconstructing it from the JSON representation, *plus*
    you'll get access to fields and better structured metadata
    that the HTML can't offer.

[22.2]: https://pip.pypa.io/en/latest/news/#v22-2

[^moreorless]: There are some notable gaps. For example, [PEP 700] added
               `upload-time` to the JSON representation only, under the
               assumption that it wouldn't be useful to package installers
               writ large. Years later, it turns out that [cooldowns]
               need this field, but that wasn't obvious in 2022!

[^yet]: Yet.

[PEP 700]: https://peps.python.org/pep-0700/

[cooldowns]: https://blog.yossarian.net/2025/11/21/We-should-all-be-using-dependency-cooldowns

