---
title: "Incident Report: Leaked GitHub Personal Access Token"
description: We responded to an incident related to a leaked
    GitHub Personal Access Token for a PyPI administrator.
authors:
  - ewdurbin
date: 2024-07-08
tags:
  - transparency
  - security
---

On June 28, 2024 <security@pypi.org> and I (Ee Durbin) were notified of
a leaked GitHub Personal Access Token for my GitHub user account, `ewdurbin`.
This token was immediately revoked,
and a review of my GitHub account and activity was performed.
No indicators of malicious activity were found.

<!-- more -->

## Timeline of events

- 2023-MM-DD[^1]:
    A GitHub Personal Access Token was created for `ewdurbin`.
    This token had push, pull, and admin access[^2]
    to all the organizations and repositories as my User,
    including `pypi`, `python`, `psf`, and `pypa`.
- 2023-03-03[^3]:
    `cabotage/cabotage-app:v3.0.0b35` pushed to hub.docker.com
    containing GitHub Personal Access Token for `ewdurbin` in a `.pyc` file.
- 2023-07-20[^3]:
    `cabotage/cabotage-app:v3.0.0b110` pushed to hub.docker.com
    containing GitHub Personal Access Token for `ewdurbin` in a `.pyc` file.
- 2024-06-21:
    `cabotage/cabotage-app:v3.0.0b35` and `cabotage/cabotage-app:v3.0.0b110`
    removed from hub.docker.com for reasons unrelated to this report[^4].
- 2024-06-28 7:09 AM Eastern:
    Brian Moussalli of JFrog reports their finding of the
    GitHub Personal Access Token for `ewdurbin` to <security@pypi.org> and Ee's
    personal email address.
- 2024-06-28 7:26 AM Eastern:
    GitHub Personal Access Token for `ewdurbin` destroyed.

## How did this happen

While developing `cabotage-app`[^5] locally, working on the build portion
of the codebase, I was consistently running into GitHub API rate limits.
These rate limits apply to anonymous access. While in production the system
is configured as a GitHub App, I modified my local files to include my own access
token in an act of laziness, rather than configure a `localhost` GitHub App.
These changes were never intended to be pushed remotely.

```diff
diff --git a/cabotage/celery/tasks/build.py b/cabotage/celery/tasks/build.py
index 0f58158..3b88b5d 100644
--- a/cabotage/celery/tasks/build.py
+++ b/cabotage/celery/tasks/build.py
@@ -395,7 +395,10 @@ def build_release_buildkit(release):
 
 
 def _fetch_github_file(
-    github_repository="owner/repo", ref="main", access_token=None, filename="Dockerfile"
+    github_repository="owner/repo",
+    ref="main",
+    access_token="0d6a9bb5af126f73350a2afc058492765446aaad",
+    filename="Dockerfile",
 ):
     g = Github(access_token)
     try:
@@ -407,7 +410,13 @@ def _fetch_github_file(
         return None
```

While I was keenly aware of the risk of leaking the token on `.py` files, `.pyc`
files containing the compiled bytecode weren't considered.

At the time, staging deployments were performed using the following script which
_attempted_ but failed to remove temporarily applied changes including the
hardcoded secret.

```bash
#!/bin/bash

generation=$(cat generation)
git stash
docker buildx build --platform linux/amd64,linux/arm64 -t cabotage/cabotage-app:v3.0.0b${generation} --push .
kubectl -n cabotage set image deployment/cabotage-app cabotage-app=cabotage/cabotage-app:v3.0.0b${generation} cabotage-app-worker=cabotage/cabotage-app:v3.0.0b${generation} cabotage-app-beat=cabotage/cabotage-app:v3.0.0b${generation}
git stash pop
echo $((generation + 1)) > generation
```

As the application had been running locally in Docker on a shared volume,
`.pyc` files containing local and uncommitted changes were still present.
A minimal [`.dockerignore` file](https://github.com/cabotage/cabotage-app/blob/c412d71b6b0ad45b7cd55d41800bf75bb0e0ea9f/.dockerignore)
at the time did not exclude `__pycache__` or `*.pyc` files from the build,
leaking the secret.

## Response

Aside from revoking the token and reviewing more or less all GitHub audit logs
and account activity available to me for possible malicious usage of the token,
a few changes have been made to mitigate future risk of this kind of leak.

Cabotage is now entirely self-hosting, which means that builds of the cabotage-app
no longer utilize a public registry[^6] and deployment builds are initiated from
clean checkouts of source only.
This mitigates the scenario of local edits making it into an image build outside
of development environments,
as well as removing the need to publish to public registries.

I have revoked the one and only GitHub access token related to my account,
and will avoid creating one in the future unless absolutely necessary,
moreover ensuring that they have a built in expiration.
Aside from this spurious usecase I cannot recall another time where a long-lived
token for my user has been helpful and having one around to potentially
leverage when I'm lazy seems risky rather then helpful.

## Takeaways

This is a great reminder
to set aggressive expiration dates for API tokens (If you need them at all),
treat `.pyc` files as if they were source code,
and perform builds on automated systems from clean source only[^7].

## Thanks

First and foremost, thanks to JFrog's team for finding and reporting this leak.
You can read their blog post on this finding
[on their blog](https://jfrog.com/blog/leaked-pypi-secret-token-revealed-in-binary-preventing-suppy-chain-attack/).

We are grateful for the entire community of security researchers
undertaking scanning of public repositories like Docker Hub and PyPI itself.
PyPI relies on the efforts of this community for detecting
[Malware uploaded to PyPI](2024-03-06-malware-reporting-evolved.md)
and
[integrates with GitHub](https://github.blog/changelog/2021-03-22-the-python-package-index-is-now-a-github-secret-scanning-integrator/)
to automatically handle leaked PyPI credentials in commits as well as
[in public issues](2023-08-17-github-token-scanning-for-public-repos.md).
Cooperation between all parties helps to improve the security of open source,
and none of us could do it alone.

---

_Ee Durbin is the Director of Infrastructure at
the Python Software Foundation.
They have been contributing to keeping PyPI online, available, and
secure since 2013._

[^1]:
    Exact date is unknown, as
    [GitHub Account Security Logs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/reviewing-your-security-log#accessing-your-security-log)
    are not available beyond 90 days.
[^2]:
    Specific permissions for this token are not known as they are not retained
    in the GitHub Account Security Log
    and were not noted before the token was destroyed.
    We've asked JFrog if their findings include the token level permissions
    and will update this post if they provide them.

    **Edit**: JFrog provided these dates from their findings on 2024-07-09.
[^3]:
    Publication dates are not known because hub.docker.com does not retain any
    history for images which have been removed.
    We've asked JFrog if their findings include the publication dates
    and will update this post if they provide them.

    **Edit**: JFrog provided these dates from their findings on 2024-07-09.
[^4]:
    `cabotage-app` had moved its builds to an automated system. The images on
    hub.docker.com were no longer necessary and were removed proactively.
[^5]:
    cabotage is the codebase that deploys the
    [warehouse codebase](https://github.com/pypi/warehouse)
    as well as related services that compose PyPI.
    You can read more about cabotage in our blog post from our
    [security audit of the codebase](2023-11-14-3-security-audit-remediation-cabotage.md).
[^6]:
    Better still, the internal private registry used for cabotage builds uses
    [fine-grained Docker authentication](https://github.com/cabotage/cabotage-app/blob/0c960f9a6683d0ced7a3be7a757edf87aff5695b/cabotage/server/models/projects.py#L586-L601)
    to allow only designated Kubernetes ServiceAccounts access to images.
[^7]:
    PyPI for instance supports
    [Trusted Publishers](https://docs.pypi.org/trusted-publishers/).
