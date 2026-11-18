# Roadmap

This page describes where PyPI's security features are going, with a focus on
attestations and trusted publishing.

## Attestations

### Current state

Attestations are optional. PyPI does not require them for uploads, and no
client enforces them on download. A project without attestations is not
considered less trustworthy by PyPI.

Trusted publishing and attestations currently support a limited set of
identity providers: GitHub Actions, GitLab CI/CD, Google Cloud, and
ActiveState. Community forges such as Codeberg are not supported yet.

Because those providers are operated by large companies, a provider can
suspend an account or change its policies in ways that affect your ability to
publish attested files, even if PyPI has no objection to your project.

### Where attestations are going

PyPI's goal is transparency, not gatekeeping. Attestations prove a link to
some machine identity; they do not prove that the identity is trustworthy.
PyPI therefore emphasizes changes in attestation status rather than the
presence of attestations alone.

PyPI does not plan to require attestations for uploads. PyPI also does not
plan to make `pip` require attestations when downloading packages. If that
changes, it will be announced well in advance.

PyPI is exploring additional attestation mechanisms, including email
attestations, and additional identity providers. There is no committed
timeline for community forges such as Codeberg.

### If you do not want to use attestations

You can keep publishing with an API token and two-factor authentication. If
your main concern is accidental releases rather than provenance, keep your
release credentials offline and require an explicit user-presence check
before uploading, for example with a hardware token or a tool such as
`tokenring`.

Uploading without attestations does not reduce the trust PyPI places in your
project. The absence of attestations is not a warning about your package.

### Who should verify attestations

Verification is for consumers who have a specific reason to care about the
build provenance of a distribution, such as organizations with a policy that
packages must be built by a known CI workflow.

Most users do not need to verify attestations. If you do verify them:

- Check that the attestation matches the file you downloaded.
- Check that the identity in the attestation is the one you expect for the
  project.
- Treat a verification failure as a reason to investigate, not as proof that
  the package is malicious.

If verification fails, report the problem to the project maintainers and, if
you believe the file was tampered with, to PyPI.

## Community forges

PyPI supports trusted publishing from GitHub, GitLab, Google Cloud, and
ActiveState. Support for community forges such as Codeberg is not available
yet, and there is no committed timeline. Projects on unsupported forges can
still publish with an API token and two-factor authentication.

## Alternate threat models

Attestations address provenance: they help answer "where did this file come
from?" They do not address every threat model. If your main concern is an
accidental release, a compromised credential, or a malicious maintainer,
attestations are not a substitute for offline credentials, two-factor
authentication, or review by a second release manager.