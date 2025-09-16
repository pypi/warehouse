---
title: Token Exfiltration Campaign via GitHub Actions Workflows
description: Incident report of a recent attack campaign targeting GitHub Actions workflows to exfiltrate PyPI tokens, our response, and steps to protect your projects.
authors:
  - miketheman
date: 2025-09-16
tags:
  - security
  - transparency
---

## Summary

We recently responded to an attack campaign where malicious actors injected code into GitHub Actions workflows 
attempting to steal PyPI publishing tokens.
PyPI was not compromised, and no PyPI packages were published by the attackers.

Attackers targeted a wide variety of repositories, many of which had PyPI tokens stored as GitHub secrets,
modifying their workflows to send those tokens to external servers.
While the attackers successfully exfiltrated some tokens, they do not appear to have used them on PyPI.

We've invalidated all affected tokens and notified the impacted project maintainers.
If you're one of them, we have emailed you from <security@pypi.org>.

<!-- more -->

You can read more about the details of the attack on [GitGuardian's blog](https://blog.gitguardian.com/ghostaction-campaign-3-325-secrets-stolen/).

## Timeline and Response

On September 5th, a GitGuardian employee used the [PyPI "Report as malware" button](./2024-03-06-malware-reporting-evolved.md)
to submit their findings for a project named `fastuuid` - namely they found a malicious GitHub Actions workflow 
attempting to exfiltrate PyPI tokens to a remote server.
No compromise on PyPI was found, tokens relating to the user accounts were invalidated,
and we reached out to the project owners to notify and help secure the account and project.

Later on September 5th, another researcher from GitGuardian emailed PyPI Security 
directly about their current findings, effectively an expansion of the previous attack.
Due to some of the contents in that email, it ended up in our inbound Spam folder,
delaying response until September 10th when I became aware of the attack via other channels,
and found the original email in the Spam folder.

After triaging the situation, I discovered another Indicator of Compromise (IoC) in the form of a URL,
which I shared with GitGuardian to assist with their ongoing investigation.

Over the course of the following few days, I reviewed the findings from the researchers.
I observed that many of the project maintainers responded to notifications from the researchers on their open source issue trackers,
either reverting the changes to their actions workflows,
or removing the affected workflows entirely from history via force-push of the repository.
Many of the maintainers also proactively rotated their PyPI tokens.

After confirming that no PyPI accounts had been compromised,
on September 15th I reached out to the maintainers of the affected projects to notify them of the situation,
to let them know that their tokens had been invalidated,
and recommend using [Trusted Publishers](./2023-04-20-introducing-trusted-publishers.md) 
with GitHub Actions to help protect their projects in the future.

## What You Can Do

If you use GitHub Actions to publish to PyPI, we recommend the following steps to protect your projects:

1. Replace long-lived tokens with Trusted Publishers.
   This is the most effective way to protect your projects from this type of attack.
   GitHub Trusted Publishers use short-lived tokens that are scoped to a specific repository,
   and expire after a short period of time.
2. Log into your account and review your security history for any suspicious activity.
   You can do this by going to your [Account Settings](https://pypi.org/manage/account/)
   and scrolling to the ["Security History" section](https://pypi.org/manage/account/#account-events).

While Trusted Publisher tokens can still be exfiltrated,
using Trusted Publishers significantly reduces the risk of compromise.

## Acknowledgements

Thanks to Charles Brossollet, Guillaume Valadon, and Gaëtan Ferry
of [GitGuardian](https://www.gitguardian.com/) for their collaboration on this issue.

This investigation and incident response is made possible by the generosity of individuals and corporations
supporting critical security efforts to better secure the Python community,
with thanks to [Alpha-Omega](https://alpha-omega.dev/).

Support these efforts and more here: https://www.python.org/sponsors/application/
