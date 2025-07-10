---
title: PyPI was subpoenaed
description: The PSF received three subpoenas from the US Department of Justice
  for PyPI user data in March and April of 2023.
authors:
  - ewdurbin
date: 2023-05-24
tags:
  - transparency
  - compliance
---

In March and April 2023, the Python Software Foundation (PSF)
received three (3) subpoenas for PyPI user data.
All three subpoenas were issued by the United States Department of Justice.
The PSF was not provided with context on the legal circumstances surrounding these subpoenas.
In total, user data related to five (5) PyPI usernames were requested.

<!-- more -->

The data request was:

1. "Names (including subscriber names, user names, and screen names);"
1. "Addresses (including mailing, residential addresses, business addresses, and email addresses);"
1. "Connection records;"
1. "Records of session times and durations, and the temporarily assigned network address (such as Internet Protocol addresses) associated with those sessions;"
1. "Length of service (including start date) and type of services utilized;"
1. "Telephone or instrument numbers (including the registration Internet Protocol address);"
1. "Means and source of payment of any such services (including any credit card or bank account number) and billing records;"
1. "Records of all Python Package Index (PyPI) packages uploaded by..." given usernames
1. "IP download logs of any Python Package Index (PyPI) packages uploaded by..." given usernames

The privacy of PyPI users is of utmost concern to PSF and the PyPI Administrators,
and we are committed to protecting user data from disclosure whenever possible.
In this case, however, PSF determined with the advice of counsel that
our only course of action was to provide the requested data.
I, as Director of Infrastructure of the Python Software Foundation,
fulfilled the requests in consultation with PSF's counsel.

We have waited for the string of subpoenas to subside, though we were committed
from the beginning to write and publish this post as a matter of transparency,
and as allowed by the lack of a non-disclosure order associated with the
subpoenas received in March and April 2023.

## Next Steps

PyPI and the PSF are committed to the freedom, security, and privacy of our users.

This process has offered time to revisit our current data and privacy standards,
which are minimal, to ensure they take into account the varied interests of
the Python community.
Though we collect very little personal data from PyPI users,
any unnecessarily held data are still subject to these kinds of requests
in addition to the baseline risk of data compromise via malice or operator error.

As a result we are currently developing new data retention and disclosure policies.
These policies will relate to
our procedures for future government data requests,
how and for what duration we store personally identifiable information such as
user access records,
and policies that make these explicit for our users and community.

Please continue to watch this blog for related announcements as policies
are finalized, published, and implemented.

---

## Details

In order to provide as much transparency as possible,
the following will detail the shape of and extent of
the data that was contained in the responses to these subpoenas.

We will not be releasing the usernames involved publicly
or to the users themselves.

### 1) Names (including subscriber names, user names, and screen names);

These were confirmed via our database records

```sql
select id, username, name from users where username = '{USERNAME}';
```

Returning:
```
id       | UUID for USERNAME
username | PyPI username
name     | Display name for user
```

And are also publicly available at `https://pypi.org/user/{USERNAME}/`.

PyPI allows users to delete their accounts.

PyPI does not allow for the `username` field to be changed without admin intervention,
and no such intervention has occurred for the users in question.
If they had, we would have provided records of those changes.

PyPI does allow for user to update their display names
and keeps no record of the history of these changes.


### 2) Addresses (including mailing, residential addresses, business addresses, and email addresses);

PyPI only stores email addresses for individual users. No physical addresses are stored.
Organization accounts who have signed up for billing (not yet live)
will be required to provide a billing address that validates to their payment method.

These were sourced from our database records and is private to PyPI.


```sql
select email, user_id from user_emails where user_id ='{UUID for USERNAME}';
```

Returning:
```
email   | An email address
user_id | UUID for USERNAME
```

PyPI allows for users to add and remove email addresses without admin intervention.
Records of these changes are kept, and no such changes were observed in our records for
the usernames in question.
If they had, we would have provided records of those changes.

### 3. Connection records

#### 3a. Project events

PyPI retains records of all changes to projects on the index,
and has since `2002-11-01 17:11:36 UTC`.

These were confirmed via our database records

```sql
select * from journals where submitted_by='{USERNAME}' order by submitted_date;
```

Returning:
```
id             | An auto incrementing integer representing the "Serial"
name           | Name of a PyPI Project
version        | Version of a PyPI Release if relevant
action         | Description of the action taken against the Project/Release
submitted_date | ISO-8601 datetime in UTC
submitted_by   | PyPI Username
submitted_from | IP Address
```

and with the exception of the `submitted_by` (PyPI username)
and `submitted_from` (IP Address) columns
are publicly available via our [XMLRPC API](https://warehouse.pypa.io/api-reference/xml-rpc.html#changelog-since-with-ids-false).

#### 3b. User events

PyPI retains records of critical user events including
account creation, emails sent, email address changes, logins, and login failures.
See [this list](https://github.com/pypi/warehouse/blob/9738ebb2ffcee91a935a6a11b224575aaf02a878/warehouse/events/tags.py#L61-L106)
for the comprehensive set of events recorded.

These were sourced from our database records

```sql
select * from user_events where source_id = '{UUID for USERNAME}' order by time desc;
```

Returning:
```
id                | UUID of the event
source_id         | UUID for USERNAME
tag               | EventTag
time              | ISO-8601 datetime in UTC
ip_address_string | IP Address
additional        | JSONB metadata about the event
ip_address_id     | UUID of associated IPAddress object
```

and are private to PyPI.

### 4. Records of session times and durations, and the temporarily assigned network address (such as Internet Protocol addresses) associated with those sessions;

PyPI does not record session durations.

Session creation (Login) times were provided as a synopsis of the data in 3b.

Sessions are not created for uploads, but the associated login events
for project uploads were provided as a synopsis of the data in 3a.

### 5. Length of service (including start date) and type of services utilized;

PyPI retains records of the date that a user account was created,
as well as the last time it was successfully logged in by any method
(web UI or command line tool for upload).


```sql
select date_joined, last_login from users where username =  {USERNAME}
```

Returning:
```
date_joined | ISO-8601 datetime in UTC
last_login  | ISO-8601 datetime in UTC
```

These were sourced from our database records and are private to PyPI.

Types of service utilized are "standard" to PyPI and include the ability to
create projects, releases, and distribution files for downloads.

### 6. Telephone or instrument numbers (including the registration Internet Protocol address);

A synopsis of all IP Addresses for each username from previous records were shared.

These were sourced from our database records and are private to PyPI.

### 7. Means and source of payment of any such services (including any credit card or bank account number) and billing records;

PyPI has no cost to use for individual users
and no such payment records or billing records exist.

### 8. Records of all Python Package Index (PyPI) packages uploaded by the given usernames

A list of all past and any current projects associated with each username was provided.

These were sourced from our database records and for past projects, are private to PyPI.

### 9. IP download logs of any Python Package Index (PyPI) packages uploaded by the given usernames

PyPI does not retain download logs for packages which include IP addresses.
Download logs are processed by a pipeline which includes GeoIP information reported by our CDN only.

These records were sourced from the [Google BigQuery Public dataset](https://docs.pypi.org/api/bigquery/) with the following queries:

```sql
SELECT * FROM `bigquery-public-data.pypi.file_downloads`
WHERE project IN ({LIST OF PROJECT NAMES FROM 8})
AND timestamp > '{START OF PERIOD IN QUESTION}';
```

---

_Ee Durbin is the Director of Infrastructure at
the Python Software Foundation.
They have been contributing to keeping PyPI online, available, and
secure since 2013._
