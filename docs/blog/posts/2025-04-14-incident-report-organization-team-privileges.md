---
title: "Incident Report: Organizations Team privileges"
description: We responded to an incident related to privileges persisting
    via Organization Teams after Members are removed from Organizations.
authors:
  - ewdurbin
date: 2025-04-14
tags:
  - transparency
  - security
---

On April 14, 2025 <security@pypi.org> was notified of a potential security concern
relating to privileges granted to a PyPI User via Organization Teams membership
persisting after the User was removed from the PyPI Organization the Team belongs to.

We validated the report as a true finding, identified all cases where this scenario
had occurred, notified impacted parties, and released a fix.
A full audit determined that all instances were accounted for,
with no unauthorized actions taken as a result of the issue.

<!-- more -->

## Timeline of events

- 2025-04-14 16:37 UTC
    A PyPI User who has been testing out our Organizations features noticed the issue
    and reported it according to our [Security Policy](https://pypi.org/security/)
    to <security@pypi.org>.
- 2025-04-14 17:02 UTC
    PyPI Security acknowledges receipt.
- 2025-04-14 17:22 UTC
    PyPI Security validates the report as a true finding.
- 2025-04-14 17:58 UTC
    PyPI Security validating test and hot fix prepared for internal review.
- 2025-04-14 18:30 UTC
    PyPI Security removes invalid Team Membership and notifies the owners of the only
    other actively impacted Organization.
    [public PR](https://github.com/pypi/warehouse/pull/17957) opened with fix.
- 2025-04-14 18:33 UTC
    Hot fix is merged.
- 2025-04-14 18:39 UTC
    Hot fix deployed and live on PyPI.
- 2025-04-14 19:06 UTC
    Security audit complete, validating that only two instances of this had
    occurred, with no unauthorized actions taken as a result of the persisted
    privileges.

## Details

PyPI Organizations have been a feature on PyPI since they were first enabled
on April 20, 2023.
This issue was introduced in the initial development of Organizations features,
and was mitigated April 14, 2025.

PyPI Organizations are quickly seeing more use as we (finally) exit our public beta
period. In the last month we have gone from 70 Community Organization beta testers
to 1,935 active Organizations[^1], so it is of little surprise that we are surfacing a few
more issues as a result.

Thanks to PyPI's strong test coverage identifying and validating the issue was rather
trivial, and getting a fix prepared and out the door was straight forward.

In total, this incident was resolved in 2 hours and 2 minutes from the time of report.

## Response

Given that this is an otherwise straightforward bug, I thought I would take a moment
to share how the issue was validated as well as how we audited.
I've replaced the specific organization, team, and user strings below,
but otherwise all of this is copied and pasted from the terminal session used
as I worked this report.

I spun up a local development environment of
[pypi/warehouse](https://github.com/pypi/warehouse)
from the current `main` branch locally and followed the reporter's steps to reproduce:

> The basic reproduce steps were:
> 
> 1. Add a user to an organization as a member
> 2. Add that member to a organization team
> 3. Remove the member from the organization

Noting that indeed, the User's team role persisted, and they could continue to act
with those privileges on PyPI.

At that point the reporter and PyPI Administrators team were notified that we had a
finding, and that review would be needed shortly to get a fix merged and deployed.

From there, I added a
[failing test](https://github.com/pypi/warehouse/pull/17957/commits/33707f0ad72e4d2efacf85fd0488e0c42fca47e6)
which further validated the issue, and got to work creating a
[patch](https://github.com/pypi/warehouse/pull/17957/commits/34a40178ee7d0e048e45867a9d8f76497f68da8c)
which turned the test green.

Now, with time to wait while a volunteer PyPI Admin returned I focused on assessing
if this was actively impacting any other organizations:

```
warehouse=> select
  o.name as organization,
  t.name as team_name,
  u.username as user,
  tr. role_name as team_role,
  ors. role_name as organization role
from
  team_roles tr
  join teams t
    on t.id=tr.team_id
  join organizations o
    on t.organization_id=o.id
  join users u
    on u.id=tr.user_id
  left outer join organization roles ors
    on ors.organization_id=t.organization_id and ors.user_id=tr.user_id
where
   ors. role_name is null;
 organization | team_name   | user      | team_role | organization_role
--------------+-------------+-----------+-----------+-------------------
 spam         | Spam-owners | spamlover | Member    | 
(1 row)
```

This query showed me that one instance of a User having an Organization Team Role
_without_ being a Member of that Organization still existed on PyPI[^2].
The reporter made clear that they had already resolved the instance from their testing.

I drafted a notice to the five users with role `Owner` on the impacted Organization, 
and took a moment to realize that this was our first time emailing Organization
Owners as a group, and that we needed to account for the fact that Users on PyPI
do not necessarily already know one-another's email addresses, as it is not required
to invite them to a Project or Organization. A quick gut-check in the PyPI Moderators
channel validated my plan to `Bcc:` all the Owners rather than `To:` them as a
group.[^3]

By that point, the volunteer PyPI Administrator was available to review the PR and
drafted e-mail. We notified the impacted Organization, and then coordinated to
open the PR publicly and approve/merge it hastily before completing a more in-depth
audit.

Luckily this audit was straightforward using our internal security records
combined with the fact that there has been minimal churn in the Organization membership
in the short time that Organizations has been in broader use.

```
warehouse=> select
  o.name, time, tag, u.username
from
  organization_events oe
  join users u
    on (additional->>'target_user_id')::uuid=u.id
  join organizations o on oe.source_id=o.id
where
  tag in ('organization:team_role:remove', 'organization:organization_role:remove')
order by time;
    name    |            time            |                  tag                  |     username      
------------+----------------------------+---------------------------------------+-------------------
 lumberjack | 2023-05-02 03:01:18.935901 | organization:organization_role:remove | sirrobin
 holygrail  | 2023-07-06 12:55:43.261593 | organization:organization_role:remove | blackknight
 ni         | 2023-09-18 12:07:17.389244 | organization:organization_role:remove | shrubbery
 parrot     | 2024-02-04 19:23:25.354344 | organization:organization_role:remove | exparrot
 spam       | 2024-08-24 01:40:22.405746 | organization:organization_role:remove | spamlover
 spam       | 2025-02-09 18:14:13.891224 | organization:team_role:remove         | eggandspam
 albatross  | 2025-03-07 06:55:29.446617 | organization:organization_role:remove | nudge
 albatross  | 2025-03-07 06:55:37.271176 | organization:organization_role:remove | wink
 cheese     | 2025-03-13 18:25:54.650905 | organization:team_role:remove         | gorgonzola
 cheese     | 2025-03-13 18:26:02.525162 | organization:team_role:remove         | camembert
 ministry   | 2025-03-20 07:53:45.616404 | organization:organization_role:remove | sillywalks
 argument   | 2025-03-31 15:52:18.186223 | organization:organization_role:remove | contradiction
 fishslap   | 2025-04-14 15:12:14.023183 | organization:organization_role:remove | danceking
 fishslap   | 2025-04-14 15:24:54.208641 | organization:organization_role:remove | danceking
 fishslap   | 2025-04-14 15:27:22.954624 | organization:team_role:remove         | danceking
```

Here, we see the `spamlover` user being removed from the `spam` Organization
on `2024-08-24`, without being removed from the team, confirming our finding from the
earlier query.

We also see the User `danceking` from the `fishslap` Organization being removed from
the Organization multiple times, before the reporter removed them from their assigned
Team.

This allowed us to confirm that beyond the already identified incidents,
no other Organizations had found this problem before without letting us know.

## Thanks

First and foremost, thanks to our reporters, Matthew Treinish and Jake Lishman
of IBM Quantum for finding and reporting this issue.

We are grateful for the entire community of security researchers and users who
find and report security issues to PyPI in accordance with our
[Security Policy](https://pypi.org/security/).
PyPI relies on the efforts of our community to help us find and resolve issues like
these before they become critical issues.
Cooperation between all parties helps to improve the security of open source,
and none of us could do it alone.

The tools and capabilities we've evolved in PyPI over the past six years have really
come to be an asset in situations like these. I'm grateful to all the contributors
and admins who have helped us to build them 💜.

---

_Ee Durbin is the Director of Infrastructure at
the Python Software Foundation.
They have been contributing to keeping PyPI online, available, and
secure since 2013._

[^1]:
    As of writing, there are 6,682 remaining Organization Requests to review.

[^2]:
    It also showed me that our modeling could certainly be improved.
    In general all the joins are fine, but the fact that a `TeamRole` is directly
    related to a `User` rather than to their `OrganizationRole` allowed for this
    disconnect in the first place.

[^3]:
    Another thing to work on moving forward. We recently added some "in-app" messaging
    for PyPI Admins and Support to contact users regarding Organization Requests,
    which could be useful for group communication with Organization Owners.
