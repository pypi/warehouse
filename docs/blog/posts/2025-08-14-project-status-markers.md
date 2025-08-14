---
title: PyPI now serves project status markers in API responses
description: >
  PyPI has implemented PEP 792, and is now serving
  project status markers in its standard HTML and JSON APIs.
authors:
  - woodruffw
date: 2025-08-14
tags:
  - security
  - integrations
---

PyPI now serves [project status markers] in its standard
[index APIs]. This allows downstream consumers (like Python package installers and
index mirrors) to retrieve project statuses programmatically and use them to
inform users when a project is archived or quarantined.

## Summary

* PyPI has implemented project status markers as proposed and accepted in
  [PEP 792].
* As of today, PyPI supports three standard statuses: **active** (the default),
  **archived**, and **quarantined**.
* Downstream consumers can now retrieve these statuses via the standard index APIs
  and use them to inform users about the state of a project.

See the [project archival] and [project quarantine] announcement posts
for additional information on PyPI's implementation of those individual statuses.

<!-- more -->

## Background

Many Python regularly find themselves asking the same
questions again and again when evaluating a new dependency:

* Is the dependency deprecated, potentially in favor of another project?
* If a vulnerability is discovered in the dependency, is it likely to be
  patched?
* Can I expect major future changes to the dependency, or is it
  "done" (i.e. feature complete)?

These questions (and many others in the domain of supply chain security)
essentially boil down to a single question:
**what is the status of this project?**

## The status quo before status markers

Before [PEP 792], Python packaging had no less than three overlapping
solutions for determining a project's status:

* Individual releases of a project could include a `Development Status`
  [trove classifier] in their metadata, such as
  `Development Status :: 7 - Inactive` to indicate that the project is no
  longer actively maintained.

    However, trove classifiers occur at the _distribution_ level, leading
    to two problems:

    1. To update a project's status, the project's maintainer must upload
       a new release with the updated classifier. This is unnecessarily
       onerous, particularly when the intent is to _stop_ updating the
       project!
    2. Classifiers do not apply retroactively, meaning that all _previous_
       releases of a project continue to have their original
       classifiers. This results in a misleading view of the project's status:
       a downstream that pins to `sampleproject==1.2.3` may fail to realize
       that `sampleproject===1.2.4` signals that the entire project is now
       inactive.

* Indices can mark individual files (or entire releases) as "yanked," per the
  [file yanking specification]. Yanked files are effectively
  soft-deleted, meaning that they'll be skipped by complying installers
  during resolution but not if explicitly pinned by the user.

    Yanking is a useful tool for mitigating accidental vulnerabilities
    or compatibility breakages in a release, but it has the same "scope"
    issue as classifiers: it applies at the file and release level,
    not at the project level.

    Moreover, the semantics of yanking aren't appropriate for all potential
    statuses: soft deletion is still disruptive, whereas statuses like
    "archived" and "deprecated" suggest that the project is still
    suitable for installation, so long as the user can be made aware of
    its status.

* PyPI itself has "project statuses," which apply to the entire project.
  These statuses were not standardized, and therefore only appeared
  on user-facing HTML pages, not in the standard APIs. This made
  them difficult to retrieve programmatically, limiting their usefulness.

Beyond these partial solutions many downstreams also apply heuristics
to determine a project's status, such as checking for recent project
(or source repository) activity or using popularity metrics like
GitHub stars as a proxy for project health. However, these heuristics
can be gamed (the unfortunately named ["starjacking" pattern]), or
outright incorrect (such as when a project is feature complete and
therefore has no recent activity).

Overall, these partial solutions and heuristics point to a need for
something better.

## Project status markers

That brings us to the new feature: project status markers.

Project status markers are a Python packaging standard derived from PyPI's
existing project statuses. The standard defines four project statuses,
which have both index-side and installer-side semantics:

* **active**: Indicates that the project is active. This is the default
  status, meaning that any project that does not explicitly
  declare a status is considered active. Active projects are
  not subject to any restrictions on upload or installation.
* **archived**: Indicates that the project does not expect to be updated
  in the future. When a project is **archived**, PyPI will not allow
  new uploads to the project, and installers are encouraged to
  inform users about the project's archival.
* **quarantined**: Indicates that the project is considered generally
  unsafe for use, e.g. due to malware. When a project is **quarantined**, PyPI
  will not offer it for installation, and installers are encouraged to
  produce a warning when users attempt to install it[^warning].
* **deprecated**: Indicates that the project is considered obsolete,
  and may have been superceded by another project. Unlike archived projects,
  deprecated projects can still be uploaded to, but installers are encouraged
  to inform users about the project's deprecation.

Of these statuses, PyPI currently supports **active**, **archived**, and
**quarantined**. PyPI doesn't support **deprecated** yet, but we'll be looking
at supporting it now that the MVP is complete.

Beyond the statuses themselves, the standard also defines an optional
"status reason" that can be used to provide additional context about the status.
PyPI doesn't currently expose status reasons, but may do so in the future.

## Consuming status markers

The standard is one thing, but let's see how to actually get status
markers from PyPI's [index APIs].

Status markers are available in both the HTML and JSON index APIs.
For the HTML API the `<meta>` fields are:

* `pypi:project-status` for the project status itself (or **active** by default)
* `pypi:project-status-reason` for the project status reason (if present)

For example:

```sh
curl --silent \
  -H "Accept: application/vnd.pypi.simple.v1+html" \
  https://pypi.org/simple/pepy/ \
    | htmlq --pretty 'head meta[name="pypi:project-status"]'
```

Yields:

```html
<meta name="pypi:project-status" content="archived">
```

Within the JSON API, the project status is available via the
top-level `project-status` object, which contains `status` and `reason`
fields corresponding to the HTML API fields above.

For example:

```sh
curl --silent \
  -H "Accept: application/vnd.pypi.simple.v1+json" \
  https://pypi.org/simple/pepy/ \
    | jq '."project-status"'
```

Yields:

```json
{
  "status": "archived",
}
```

## Conclusion

Starting today, Python package installers and other index consumers can
retrieve status markers from PyPI's standard index APIs.

Our hope is that downstreams *will* consume these markers, and use them
as suggested by the standard. In particular we hope that installers like
[pip] and [uv] will signal relevant statuses to users, helping them
form a better picture of the status of their dependencies as well as set
policies controlling which statuses are acceptable for installation.

## Acknowledgements

[PEP 792] was authored by [William Woodruff] (Astral) and
[Facundo Tuesca] (Trail of Bits). We'd like to thank [Donald Stufft] for being
the PEP's sponsor and PEP delegate. Additionally, we'd like to thank
[Dustin Ingram] and [Mike Fiedler] for their review and feedback on the PEP
and the associated changes to PyPI.

The funding for this feature’s development comes in part from
[Alpha-Omega]. Alpha-Omega’s mission is to protect society by catalyzing
sustainable security improvements to the most critical open-source software
projects and ecosystems.

[project status markers]: https://packaging.python.org/en/latest/specifications/project-status-markers/
[index APIs]: https://docs.pypi.org/api/index-api/
[PEP 792]: https://peps.python.org/pep-0792/
[project archival]: 2025-01-30-archival.md
[project quarantine]: 2024-12-30-quarantine.md
[trove classifier]: https://pypi.org/classifiers
[file yanking specification]: https://packaging.python.org/en/latest/specifications/file-yanking/
["starjacking" pattern]: https://capec.mitre.org/data/definitions/693.html
[Alpha-Omega]: https://alpha-omega.dev/
[Facundo Tuesca]: https://github.com/facutuesca
[William Woodruff]: https://github.com/woodruffw
[Donald Stufft]: https://github.com/dstufft
[Dustin Ingram]: https://github.com/di
[Mike Fiedler]: https://github.com/miketheman
[pip]: https://pip.pypa.io/
[uv]: https://docs.astral.sh/uv/

[^warning]: This warning is technically moot, as PyPI itself will not offer
            any files from quarantined projects for installation.
            However, the warning can still help users understand _why_
            their installation has failed, and is therefore recommended
            by the standard.
