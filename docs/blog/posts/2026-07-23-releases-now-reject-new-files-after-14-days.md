---
title: "Releases now reject new files after 14 days"
description: PyPI no longer allows publishing new files to releases older than 14 days.
authors:
  - sethmlarson
date: 2026-07-23T12:00:00
tags:
  - security
meta:
  - name: fediverse:creator
    content: "@sethmlarson@mastodon.social"
---

The Python Package Index (PyPI) now rejects new files being uploaded to releases
that are older than 14 days. This restriction was [put in place](https://github.com/pypi/warehouse/pull/19727) to prevent
old and long-stable releases being poisoned in case publishing tokens or workflows
of PyPI projects were compromised. As far as we
are aware this has not yet been abused, but there is no technical reason
beyond that attackers weren't aware it was possible.

Users should not yet rely on this behavior as there are no defined semantics
for “releases no longer accepting new files” or APIs available to confirm
the state of the release. Instead, these semantics will be defined once
“Upload 2.0 API” and “Staged Previews” have been standardized by
[PEP 694](https://peps.python.org/pep-0694/).

The [discussion of this behavior began](https://discuss.python.org/t/restricting-open-ended-releases-on-pypi/43566) during PEP 740 (Digital Attestations) back
in January 2024. The discussion was [restarted in March 2026](https://discuss.python.org/t/restricting-open-ended-releases-on-pypi/43566/34) after the popular packages [LiteLLM and Telnyx
were compromised](https://blog.pypi.org/posts/2026-04-02-incident-report-litellm-telnyx-supply-chain-attack/).
These packages were compromised due to a “[mutable reference](https://mikael.barbero.tech/blog/post/2026-03-24-stop-trusting-mutable-references/)” in these projects'
usage of the Trivy GitHub Action.

Originally the discussion stalled due to some projects depending on
this behavior to add support for new Python versions to already-published releases.
To quantify how disruptive this change would be to existing workflows,
the PyPI database was queried for [projects that have published
new files to old releases](https://discuss.python.org/t/restricting-open-ended-releases-on-pypi/43566/48) (bucketed by number of days since).
Later specifically `cp314` wheels were queried for the top 15,000 packages, revealing
that [only 56 projects of 15,000](https://discuss.python.org/t/restricting-open-ended-releases-on-pypi/43566/63) had published a 3.14-compatible wheel
more than 14 days after a release was available.

This topic was brought to the [Packaging Summit at PyCon US 2026](https://hackmd.io/k0C-RAIVRnu-YXoDFgABvA) by PyPI Safety & Security
Engineer, Mike Fiedler. The rough consensus of the discussion was that the summit attendees thought
it was “acceptable to require users to bump to the next version” to support
new Python versions. With the data and consensus in hand, Seth [moved forward with
a patch](https://github.com/pypi/warehouse/pull/19727) to reject new files on
old releases which was merged July 8th, 2026.

This change will protect Python users and reduce the amount of “cleanup”
work associated with project compromises for PyPI admins. This restriction
also means that compromises don't put releases into an indeterminate and
confusing state of both "compromised" and "not compromised", where only a subset
of files could be poisoned with malware. Stay tuned for the future where
Upload 2.0 API provides semantics for releases that are “closed” instead
of “open”.

Seth Larson and Mike Fiedler’s work at the Python Software Foundation is
supported by [Alpha-Omega](https://alpha-omega.dev/).
