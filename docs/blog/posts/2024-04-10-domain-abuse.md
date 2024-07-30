---
title: "Malware Distribution and Domain Abuse"
description: Domain names used in malware attack, and how PyPI handled it.
authors:
  - miketheman
date: 2024-04-10
tags:
  - security
  - transparency
---

A package named `yocolor` was uploaded to PyPI
designed assist with malware distribution to targets.

The package was removed from PyPI, curtailing its potential impact to users.

This incident differs from the usual malware package removals,
as it involved a domain name that was used in the attack
to host the second stage of the malware distribution.

Checkmarx Security Research Team have [published an in-depth blog](https://checkmarx.com/blog/over-170k-users-affected-by-attack-using-fake-python-infrastructure/)
on the specific behaviors - read their report for how it works.

Since PyPI is only involved with what Checkmarx called "Stage 1" of the attack,
I'll focus on the package removal and domain abuse follow up here.

<!-- more -->

## Timeline

* 2024-03-05 01:09 UTC - Package `yocolor` version `0.4.6` uploaded
* 2024-03-05 06:17 UTC - First inbound report from Phylum researchers
* 2024-03-05 23:40 UTC - Second inbound report from independent researcher
* 2024-03-06 17:16 UTC - Package `yocolor` removed from PyPI
* 2024-03-06 17:20 UTC - Email sent to domain registrar, regarding the abuse of `pypihosted.org`
* 2024-03-12 08:00 UTC - Registrar responds, they have notified the domain holder
* 2024-03-18 - `pypihosted.org` domain nameservers removed
* 2024-03-25 - Checkmarx blog published

In reading the Checkmarx blog,
they show another domain registered from the same user,
with a similar pattern: `pythanhosted.org`.
It's still unclear to me how exactly this domain was used,
because I wasn't able to find a record of it on PyPI,
but it was registered by the same entity, same registrar.

This time, I contacted the registrar, as well as Cloudflare,
where the nameservers were configured.

* 2024-03-25 18:30 UTC - Email sent to domain registrar, regarding the abuse of `pythanhosted.org`
* 2024-03-25 17:05 UTC - Abuse report [submitted to Cloudflare](https://abuse.cloudflare.com/phishing).
* 2024-03-25 17:06 UTC - Cloudflare automated response, clarifying that I may not receive further notice.
* 2024-03-29 20:47 UTC - Registrar responds, they have notified the domain holder
* 2024-04-04 - `pythanhosted.org` domain nameservers removed

## Overall Impact

In the time frame it was live on PyPI,
the `yocolor` project was downloaded in total 116 times.

Many of these downloads are from package mirrors
([bandersnatch](https://pypi.org/project/bandersnatch/) among others),
copying packages to their own infrastructure.
Other downloads may be from from security inspections and analysis - including our own.

For example, a researcher may download a package to inspect the contents,
and when they report it to PyPI, the package is re-inspected by PyPI Admins,
which would count as another download.

There's no definitive way to know how many end users installed the package
into an environment that actually executed the malware,
but as evidenced by the Checkmarx blog,
there were at least a few that have a wider impact on the intended targets.

## Technique: Masquerading

In the package metadata, the attacker used links to
the GitHub account of the creator of the package `colorama`,
to create a sense of legitimacy.
This technique is also known as [StarJacking](https://capec.mitre.org/data/definitions/693.html).

`colorama` is a popular package, used by packages
like `click`, `pip-tools` and others.
This is not the first time attackers have used
a "color" themed package to distribute malware.

When choosing packages to install,
ensure you're typing the package name correctly,
or even copy it from PyPI directly to avoid typos.

While this isn't ever going to be a guarantee of safety,
it's a good practice to follow and can minimize the risk of typosquatting attacks.

More importantly, if someone you don't know very well
is recommending `pip install` something (or a similar package manager command),
this is usually a moment to pause and consider the source of the recommendation.

## Service Provider Response

### Registrar

I re-read ICANN's [Registrar Abuse Reports](https://www.icann.org/resources/pages/abuse-2014-01-29-en),
and from my non-expert interpretation, I believe the registrar operated within the bounds of the policy.
I find it interesting that the registrar took 6 days to respond to the initial report,
only to inform me they have sent it along to the domain registrant (presumably the attacker),
which in and of itself seems like the wrong way to handle abuse reports.

The time-to-respond seems larger than what I'd expect,
but given there does not appear to be an SLA or expectation set by ICANN,
I can only assume that the registrar is operating within their own internal guidelines.

### Hosting Provider

The domains used in this attack were both hosted on Cloudflare,
as evidenced by their nameservers.

When reporting Malware abuse to Cloudflare, [their form](https://abuse.cloudflare.com/phishing) states:

> Because Cloudflare does not have the ability to remove content from a website,
> it is our practice to forward abuse complaints to entities
> like the hosting provider and/or website owner to follow up.

The form shows two checkboxes that cannot be deselected,
that the details of the report will be forwarded to
the website hosting provider and website owner.

This stood out to me, to be aware that anything submitted
may be shared with the alleged attacker.

Cloudflare sent an automated response via email
within a few minutes of my submission,
confirming receipt, and reminding em that they may not follow up with me.

## Domain Visibility

I was able to snag some details from [CompleteDNS](https://completedns.com/dns-history/)
about the domain name history to help with the timeline.

Here's a couple of screenshots of the domain history for the two domains:

![Screenshot detailing the history of domain name registration for `pypihosted.org`. The domain was created on February 3, 2024 and the nameservers were updated three times. The domain was then dropped on March 18, 2024.](../assets/2024-04-10-domain-abuse/screenshot-pypihosted.png)
![Screenshot detailing the history of domain name registration for `pythanhosted.org`. The domain was created on March 15, 2024. The domain was then dropped on April 4, 2024.](../assets/2024-04-10-domain-abuse/screenshot-pythanhosted.png)

There may be other services that provide similar information,
but I found this one to be useful in this case.
If you've got another one that you like, let me know!

## Closing Thoughts

Installing packages from PyPI is a trust relationship,
and I hope that this transparency helps to reinforce that trust.
With our volunteer PyPI Admins, community of security researchers,
and the vigilance of the wider Python community,
we can all work towards safer software distribution.

The kind of follow-up work done here
is not something that volunteers have often had the time to do,
and I'm grateful for the support to ensure these kinds of activities are possible.

Read about how we've [evolved malware reporting](./2024-03-06-malware-reporting-evolved.md)
to bring the security community closer to PyPI Administrators.

There's still a lot of work to do in this space,
and [we're hiring a Support Specialist](./2024-03-20-announcing-a-pypi-support-specialist.md)
to help us manage the increased capacity
and allow us to keep pace with PyPI's seemingly unstoppable growth.

Join us!

---

_My role is made possible with the support from
[Amazon Web Services Open Source](https://aws.amazon.com/opensource/),
[Georgetown CSET](https://cset.georgetown.edu/),
the [PSF](https://www.python.org/psf/) and their sponsors._

*[ICANN]: [Internet Corporation for Assigned Names and Numbers](https://icann.org)
*[SLA]: [Service Level Agreement](https://wikipedia.org/wiki/Service-level_agreement)
