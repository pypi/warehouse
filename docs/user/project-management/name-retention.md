---
source: https://peps.python.org/pep-0541/
title: Name Retention
---

# Name Retention

!!! note

    This page contains the policy components [PEP 541]. The procedural
    components of the PEP (Abstract, Rationale, etc.) have been omitted
    from this page, but can be found in the PEP itself.

[PEP 541]: https://peps.python.org/pep-0541/

## Specification

The main idea behind this document is that the Package Index serves the
community. Every user is invited to upload content to the Package Index under
the Terms of Use, understanding that it is at the sole risk of the user.

While the Package Index is not a backup service, the maintainers of the Package
Index do their best to keep that content accessible indefinitely in its
published form. However, in certain edge cases the greater community’s needs
might overweigh the individual’s expectation of ownership of a package name.

The use cases covered by this document are:

- Abandoned projects:
    - continued maintenance by a different set of users; or
    - removal from the Index for use with a different project.
- Active projects:
    - resolving disputes over a name.
- Invalid projects:
    - projects subject to a claim of intellectual property infringement.
    - The proposed extension to the Terms of Use, as expressed in the
      Implementation section, will be published as a separate document on the
      Package Index, linked next to existing Terms of Use in the front page
      footer.

## Implementation

### Reachability

The user of the Package Index is solely responsible for being reachable by the
Package Index maintainers for matters concerning projects that the user owns. In
every case where contacting the user is necessary, the maintainers will try to
do so at least three times, using the following means of contact:

- the e-mail address on file in the user’s profile on the Package Index;
- the e-mail address listed in the Author field for a given project uploaded to
  the Index; and
- any e-mail addresses found in the given project’s documentation on the Index
  or on the listed Home Page.

The maintainers stop trying to reach the user after six weeks.

### Abandoned projects

A project is considered _abandoned_ when ALL of the following are met:

- owner not reachable (see Reachability above);
- no releases within the past twelve months; and
- no activity from the owner on the project’s home page (or no home page
  listed).

All other projects are considered active.

### Continued maintenance of an abandoned project

If a candidate appears willing to continue maintenance on an _abandoned_
project, ownership of the name is transferred when ALL of the following are met:

- the project has been determined _abandoned_ by the rules described above;
- the candidate is able to demonstrate their own failed attempts to contact the
  existing owner;
- the candidate is able to demonstrate improvements made on the candidate’s own
  fork of the project;
- the candidate is able to demonstrate why a fork under a different name is not
  an acceptable workaround; and
- the maintainers of the Package Index don’t have any additional reservations.

Under no circumstances will a name be reassigned against the wishes of a
reachable owner.

### Removal of an abandoned project

Projects are never removed from the Package Index solely on the basis of
abandonment. Artifacts uploaded to the Package Index hold inherent historical
value.

An _abandoned_ project can be transferred to a new owner for purposes of reusing
the name when ALL of the following are met:

- the project has been determined abandoned by the rules described above;
- the candidate is able to demonstrate their own failed attempts to contact the
  existing owner;
- the candidate is able to demonstrate that the project suggested to reuse the
  name already exists and meets notability requirements;
- the candidate is able to demonstrate why a fork under a different name is not
  an acceptable workaround; download statistics on the Package Index for the
  existing package indicate project is not being used; and
- the maintainers of the Package Index don’t have any additional reservations.

### Name conflict resolution for active projects

The maintainers of the Package Index are not arbiters in disputes around
_active_ projects. There are many possible scenarios here, a non-exclusive list
describing some real-world examples is presented below. None of the following
qualify for package name ownership transfer:

- User A and User B share project X. After some time they part ways and each of
  them wants to continue the project under name X.
- User A owns a project X outside the Package Index. User B creates a package
  under the name X on the Index. After some time, User A wants to publish
  project X on the Index but realizes name is taken. This is true even if User
  A’s project X gains notability and the User B’s project X is not notable.
- User A publishes project X to the Package Index. After some time User B
  proposes bug fixes to the project but no new release is published by User A.
  This is true even if User A agrees to publish a new version and later doesn’t,
  even if User B’s changes are merged to the source code repository for project
  X.

Again, the list above is not exclusive. The maintainers of the Package Index
recommend users to get in touch with each other and solve the issue by
respectful communication (see the [PSF Code of Conduct]).

[PSF Code of Conduct]: ../python.org/code-of-conduct/index.md

### Invalid projects

A project published on the Package Index meeting ANY of the following is
considered invalid and will be removed from the Index:

- project does not conform to Terms of Use;
- project is malware (designed to exploit or harm systems or users directly, to
  facilitate command-and-control attacks, or perform data exfiltration);
- project is spam (designed to advertise or solicit goods or services);
- project contains illegal content;
- project violates copyright, trademarks, patents, or licenses;
- project is name squatting (package has no functionality or is empty);
- project name, description, or content violates the Code of Conduct;
- project uses obfuscation to hide or mask functionality; or
- project is abusing the Package Index for purposes it was not intended.

The Package Index maintainers pre-emptively declare certain package names as
unavailable for security reasons.

### Intellectual property policy

It is the policy of Python Software Foundation and the Package Index maintainers
to be appropriately responsive to claims of intellectual property infringement
by third parties. It is not the policy of the Python Software Foundation nor the
Package Index maintainers to pre-screen uploaded packages for any type of
intellectual property infringement.

Possibly-infringing packages should be reported to [legal@python.org] and
counsel to the Python Software Foundation will determine an appropriate
response. A package can be removed or transferred to a new owner at the sole
discretion of the Python Software Foundation to address a claim of infringement.

[legal@python.org]: mailto:legal@python.org

A project published on the Package Index meeting ANY of the following may be
considered infringing and subject to removal from the Index or transferral to a
new owner:

- project contains unlicensed copyrighted material from a third party, and is
  subject to a properly made claim under the DMCA;
- project uses a third party’s trademark in a way not covered by nominal or fair
  use guidelines;
- project clearly implicates a patented system or process, and is the subject of
  a complaint; or
- project is subject to an active lawsuit.

In the event of a complaint for intellectual property infringement, a copy of
the complaint will be sent to the package owner. In some cases, action may be
taken by the Package Index maintainers before the owner responds.

### The role of the Python Software Foundation

The [Python Software Foundation] is the non-profit legal entity that provides
the Package Index as a community service.

[Python Software Foundation]: https://www.python.org/psf/

The Package Index maintainers can escalate issues covered by this document for
resolution by the Packaging Workgroup if the matter is not clear enough. Some
decisions require additional judgement by the Board, especially in cases of Code
of Conduct violations or legal claims. Recommendations made by the Board are
sent to the [Packaging Workgroup] for review.

[Packaging Workgroup]: https://wiki.python.org/psf/PackagingWG/

The Packaging Workgroup has the final say in any disputes covered by this
document and can decide to reassign or remove a project from the Package Index
after careful consideration even when not all requirements listed here are met.

### How to request a name transfer

If you want to take over an existing project name on PyPI, these are the steps
to follow:

- Try to contact the current owner(s) directly: email them and open an issue if
  you can find a related repository. The processes described here are meant as a
  last resort if the owner cannot be contacted.
- Check the criteria above to see when a transfer is allowed. In particular, the
  criteria for [reusing a name for a different project] are more stringent than
  for [continuing maintenance of the same project] - although it’s not easy to
  get a name transferred in either case.
- Search the [PyPI Support issues] to see if anyone else is already requesting
  the same name.
- If all the criteria are met to transfer ownership of the name,
  [open a new issue] to request it, detailing why you believe each relevant
  criterion is satisfied.

[reusing a name for a different project]: #removal-of-an-abandoned-project
[continuing maintenance of the same project]: #continued-maintenance-of-an-abandoned-project
[PyPI Support issues]: https://github.com/pypa/pypi-support/issues
[open a new issue]: https://github.com/pypa/pypi-support/issues/new?labels=PEP+541&template=pep541-request.yml&title=PEP+541+Request%3A+PROJECT_NAME
