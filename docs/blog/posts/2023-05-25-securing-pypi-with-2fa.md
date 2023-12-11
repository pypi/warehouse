---
title: Securing PyPI accounts via Two-Factor Authentication
description: PyPI will require all users who maintain projects or organizations to enable one or more forms of two-factor authentication (2FA) by the end of 2023.
authors:
  - dstufft
date: 2023-05-25
tags:
  - security
  - 2fa
---

One of the key security promises that PyPI makes is that when you're downloading
something, that only the people associated with that project are going to be able
to upload, delete, or otherwise modify a project. That when you look at that
project and see that it is owned by someone that you trust, that you can be
assured that nobody else is making changes to that package on PyPI.

<!-- more -->

This promise is predicated on the security of each and every individual account
on PyPI used to create and maintain a Python project. In the past we've taken
steps to safeguard these accounts by
[blocking compromised passwords](https://caremad.io/posts/2018/08/pypi-compromised-passwords/), strong 2FA support using
[TOTP](https://github.com/pypi/warehouse/pull/5567) and
[WebAuthN](https://github.com/pypi/warehouse/pull/5795),
[support for API tokens with offline attenuation](https://pypi.org/help/#apitoken),
[enrolling the most downloaded projects into mandatory 2FA](https://pypi.org/security-key-giveaway/),
and [enabling short lived tokens for upload](https://blog.pypi.org/posts/2023-04-20-introducing-trusted-publishers/).

Today, as part of that long term effort to secure the Python ecosystem, we are
announcing that *every* account that maintains any project or organization
on PyPI will be required to enable 2FA on their account by the end of 2023.

Between now and the end of the year, PyPI will begin gating access to certain
site functionality based on 2FA usage. In addition, we may begin selecting
certain users or projects for early enforcement.

## What can I do to prepare?

The most important things you can do to prepare are to enable 2FA for your
account as soon as possible, either with a
[security device](https://pypi.org/help/#utfkey) (preferred) or an
[authentication app](https://pypi.org/help/#totp) and to switch to using either
[Trusted Publishers](https://docs.pypi.org/trusted-publishers/) (preferred) or
[API tokens](https://pypi.org/help/#apitoken) to upload to PyPI.

## Why Use 2FA?

Account takeover attacks typically stem from someone using an insecure password:
perhaps it was easy to guess, or it was reused and appeared in a breach. With
that insecure password, an attacker is able to gain control over a maintainers
account and begin to take actions as if they were that user.

This is particularly problematic on a site like PyPI, where the actions that a
person can take include releasing software that might be used by people world
wide, allowing an attacker to install and execute software on unsuspecting
user's computers. [Account takeover attacks have been previously used to
compromise PyPI users in this
way](https://python-security.readthedocs.io/pypi-vuln/index-2022-05-24-ctx-domain-takeover.html).

Two-factor authentication immediately neutralizes the risk associated with a
compromised password. If an attacker has someone's password, that is no longer
enough to give them access to that account.

## Why every project or organization maintainer?

There's two ways to think about this question:

- Why every project and organization maintainer instead of just some subset of
  them (based on popularity, purpose, whether that user uses their account,
  etc)?
- Why only maintainers and not every single user?

Not every account on PyPI has the same value to an attacker. An account with
access to the most downloaded project on PyPI can be used to attack far more
people than an account with access to the least downloaded project.

However, it only takes one compromised project in someone's dependency set to
compromise their computer. The attacker doesn't care if they get you from a
widely used or a niche project, just that they got you. Even worse, once
compromised, an attacker can extend that attack to attack *other* systems,
including other projects on PyPI that the now compromised person maintains.

Given that it only takes one compromised project, no matter how many downloads
it gets [^1], to compromise someone we want to ensure that every project is
being protected by 2FA.

On the flipside, an account without access to any project cannot be used to
attack anyone [^2] so it is a very low value target.

We recognize that enabling 2FA for an account imposes a non zero cost both for
the owner of that account *and* for PyPI [^3], so forcing that on accounts that
cannot affect anyone but themselves is not an effective use of limited
resources. In addition, from a practical view, the standard 2FA flow that most
people are used to and that PyPI implements also involves adding a 2FA token
to an existing account rather than forcing it to be part of the registration
flow.

Our expectation is that for users who currently are not a project maintainer or
organization member, the ultimate experience will be whenever they attempt to
take some action that would require them to add 2FA (creating a new project,
accepting an invite, making an organization, etc) they will be prompted to add
2FA to their account before they can proceed.

## Why now?

The direction of many projects in or serving the Open Source community in the
last 5-10 years has been an increasing focus on supply chain security,
preventing attacks that are being delivered through the "supply chain", namely
the services and tooling used to create and consume software.

In July of 2022, we announced
[a security key giveway](https://pypi.org/security-key-giveaway/) in conjunction
with a plan to begin mandating 2FA for the top 1% of projects on PyPI by download
count.

The initial announcement of that mandate to the top 1%
of projects and the related giveaway was met with mixed reactions, ranging from
people applauding the effort to people deciding to distribute their code on
places other than PyPI. We planned to limit this to the projects in the top 1%
of downloads because those are likely he highest value targets for an attacker,
and because we were concerned about the impact of such a mandate on both the
maintainers of projects on PyPI, and on the support burden of the PyPI team
itself.

At that time last year, we did not have any plans or expectations on widening
our net of users that would fall under that mandate, other than would occur
naturally as projects rose in popularity to be part the top 1%.

However, in the year since then a few things have changed.

- We've gotten a lot more confident in our 2FA implementation and in what the
  impact to enabling it is for both people publishing to PyPI, and to the PyPI
  team itself.
- We've shipped features like
  [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) that help
  remove some of the overheard of 2FA has on publishing (by far the most common
  action users do).
- GitHub has furthered it's
  [plans to mandate 2FA for all contributors](https://github.blog/2022-05-04-software-security-starts-with-the-developer-securing-developer-accounts-with-2fa/)
  on their platform, making more people already (or soon will be) prepared to cope
  with the requirements of having 2FA.
- The PSF has received funding to hire a
   [PyPI Safety and Security Engineer](https://blog.pypi.org/posts/2023-05-09-announcing-pypi-safety-and-security-engr-role/).
  While the role is not meant to purely handle support requests, having
  dedicated focus on the overall security posture, as well as the
  implementation specifics will improve PyPI as a whole for both
  users and project maintainers, and will help alleviate some of the
  pressures on PyPI's volunteers.
- The workload to support end users relies heavily on a very small group of
  volunteers. When an user account report is seen by our trusted admins, we have
  to take time to properly investigate. These are often reported as an emergency,
  red-alert-level urgency. By mandating 2FA for project maintainers, the
  likelihood of account takeovers drop significantly, reserving the emergency
  status for truly extraordinary circumstances. Account recovery becomes part of
  normal routine support efforts instead of admin-level urgency.

All of these together help lead us to the conclusion that we can widen our
mandate to *all* project maintainers on PyPI, while minimizing the impact on
both project maintainers and PyPI administrators, and to do so in a way that
improves the sustainability of PyPI and the wider Python ecosystem.

## Isn't supply chain security a corporate concern?

There are some people who believe that efforts to improve supply chain security
benefits only corporate or business users, and that individual developers should
not be asked to take on a uncompensated burden for their benefit.

We believe this is shortsighted.

A compromise in the supply chain can be used to attack individual developers the
same as it able to attack corporate and business users. In fact, we believe
that individual developers, are in a *more* vulnerable position than corporate
and business users. While businesses are generally able to hire staff and devote
resources to vetting their dependencies, individual developers generally are
not, and must expend their own limited free time to do so [^4].

To make matters worse for the individual, in the case of a compromise a business
is more likely going to have experts available to them to detect and remediate
the compromise, while the individual has to do this on their own. At the extreme
ends, businesses often have insurance to compensate them for any losses incurred
while the individual almost always does not.

We recognize that supply chain security effects *everyone*, no matter how big
or how small they are, and we are dedicated to protecting *all* our users.

---

_Donald Stufft is a PyPI administrator and maintainer of the Python Package Index since 2013._


[^1]: *Technically* a project with 0 downloads is effectively the same as a
      non-existent project, but it's easier to draw the line between
      non-existent and existent than it is to draw the line between 0 and 1
      downloads. This is particularly true on PyPI, where a large network of
      mirrors and scanners mean that *no* projects truly get downloaded exactly
      0 times.
[^2]: Except maybe the account owner themselves, by denying them access to their
      account.
[^3]: For end users it forces them to purchase some kind of hardware token *OR*
      to use some sort of TOTP application. In both cases it forces them to keep
      track of something else besides their password and changes the login flow
      from what they are used to. For PyPI it increases the chance that someone
      may get locked out of their account, requiring intervention by administrators.
[^4]: Not for nothing, but PyPI is also an Open Source project, run largely by
      volunteers, and cleaning up after a compromise on PyPI is something that
      affects those volunteers significantly.
