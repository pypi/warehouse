---
title: Reducing Stored IP Data in PyPI
description: PyPI has stopped using IP data when possible, and is continuing to reduce the amount of IP data stored overall.
authors:
  - miketheman
date: 2023-05-26T15:00:00
tags:
  - security
  - transparency
---

Hi there! I'm Mike, the newest member of the PyPI admin team. Nice to meet you!

## TL;DR

We've been working on reducing the amount of IP address data we store,
and we're making progress.

<!-- more -->

## What's this about?

If you've read some of the other blogs here, you may have noticed that
we've been working on a number of security and privacy improvements.

A few months ago we started exploring what it would take
to remove the concept of IP addresses from our stack,
and retain the ability to safely manage the platform.

Some places of where IP data was historically used:

- web access logs
- user events (login,. logout, password reset, et al)
- project events (creation, new releases, new file uploads, yanks, et al)
- organization/team membership events ([new!](./2023-04-23-introducing-pypi-organizations.md))
- journal entries (private to PyPI admins)

Security is a spectrum - where on one extreme, it's the wild west, no security.
On the other extreme, everything is locked down, impossible to use.
We constantly have to balance the needs and desires of our users
with the needs of running a sustainable, trusted platform.

A similar mindset can be applied to privacy - where we must strike the balance
between providing a manageable service, and protecting the privacy of our users.

The two main approaches we've pursued in the short term are:

- Evaluate whether we need to store IP data at all
- Whenever possible, use alternatives to IP data

I'll provide a couple of examples demonstrating the above.

## Do we need the IP data?

As we evaluated the different places we stored IP data,
we learned that our Journal entries (similar to an append-only transaction log)
were never exposed beyond admin users, and even then, used for admin display only.

We never share that via API, or used it for operational purposed.
So we audited the code, removed calls to stop writing the column, and dropped it.

Woohoo!

Other places where we currently still need IP data include rate limiting,
and fallbacks until we have backfilled the IP data with hashes and geo data.
Our modern approach has evolved from using the IP data at display time to find
the relevant geo data, to storing the geo data directly in the database.

Another use case is for handling abuse - we need to be able to identify
the source of abuse, and take action to prevent it.
We're thinking about how to manage that without storing IP data,
but we're not there yet.

## Alternatives to IP data

For the other places where we stored IP data,
we asked ourselves - could we use an alternative?

We can't store what we don't see, so we explored what we could do to
reduce the amount of IP data we see.

Pretty much every request to PyPI is served via our CDN partner, Fastly.
They provide a number of features, including the ability to
[add custom headers](https://docs.fastly.com/en/guides/adding-or-modifying-headers-on-http-requests-and-responses).
We leverage this ability already for a number of things,
like informing the warehouse code of the inbound encoding of the request or language.

We explored whether we could use this to add a hash of the IP address,
and use that instead of the IP address itself.
Fastly can also provide some basic geographic info about the IP address,
which served our purpose of showing the user where they had connected from.

Using this approach, we have Fastly pass along an already-hashed IP address,
as well as the geographic data, to our backend, and store those for later use.

Another spot we identified was web access logs.
We don't need real IP addresses there,
as we rarely use them for anything other than low-level debugging,
so a stable, hashed value serves the purpose of correlating requests.

For the requests that Fastly doesn't serve, we're already hashing the IP address
ourselves prior to storage, so we could "see" the IP address briefly,
but we try to avoid storing it.
We don't get get the geo data for these requests,
we're thinking of creative and sustainable solutions already.

## Questions and Answers

I tried to think up some questions you might have, and answer them here.
If you have more, please feel free to reach out to us!

**Q:** Is a hashed IP address secure?

**A:** It's more secure than a plain IP address, for sure.
We apply a [salt](https://en.wikipedia.org/wiki/Salt_(cryptography)) (known value)
to the IP address before hashing it.
It's not a perfect solution, but it's a step in the right direction.

The hash is non-reversible, but since the known address space is relatively small,
it's possible to brute force the hash to determine the original IP address.
By applying a salt, we require someone to possess **both** the salt
and the hashed IP addresses to brute force the value.
Our salt is not stored in the database while the hashed IP addresses are,
we protect against leaks revealing this information.

**Q:** Is this a response to the subpoenas?

**A:** No, we started exploring this [back in 2020](https://github.com/pypi/warehouse/issues/8158),
with a long term goal to increase end-user security,
while retaining the ability to effectively steer the platform.
We picked it up recently as we explored our CDN partner's options for geo IP data.

**Q:** Are we done?

**A:** Nope! Security is an ongoing journey,
and we're making strong strides to accomplish this goal.
We still have some work to do to replace IP data in our models,
after we've backfilled our models with the hashed IP data and relevant geo data,
and clean up some of the code.

**Q:** What's next?

**A:** I can't predict every future step we're likely to take,
but some things we're considering:

- Reevaluate the need for IP data in Event history **forever**,
  remove it after a period of time
- Explore whether we can use a CDN for all requests
- Determine if there's a better mechanism than Journal Entries, and replace them

We believe the steps we're taking are in the right direction,
and we're excited to share our progress with you.
Hopefully this enriches your understanding of the work we're doing,
in support of maintaining a secure, trusted platform.

Thanks for reading!

---

_Mike Fiedler is a PyPI administrator
and maintainer of the Python Package Index since 2022._
