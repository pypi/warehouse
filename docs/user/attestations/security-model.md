---
title: Security Model and Considerations
---

# Security model and considerations

## General considerations

PyPI's support for attestations is built on top of a combination
of [Trusted Publishing] and [Sigstore's "keyless signing"] ability.
See below for security considerations for each.

### Trustworthiness

!!! note

    TL;DR: An attestation will tell you **who** produced a
    PyPI package, but not **whether** you should trust them.

Like with all signing schemes, it's tempting to treat the *presence* of
an attestation as proof of a package's *trustworthiness*.

However, this is **not** what an attestation (or any kind of signature)
conveys. At its core, a valid signature for some identity conveys a
proof of **authenticity**: if the signature is verifiable against a key,
then we know that the identity that controls that key produced the signature
and is saying *something* about the signed-over data.

In other words: a valid signature asserts **authenticity**, but it does **not**
tell the verifying party (e.g., a user installing packages from PyPI) **whether**
they should trust the identity that holds the key.

As a concrete example: PyPI serves `sampleproject-4.0.0.tar.gz`, which is
[attested] by [pypa/sampleproject] on GitHub. This is a proof that
`sampleproject-4.0.0.tar.gz` is authentic for that identity, but it does **not**
tell the user **whether** they should trust [pypa/sampleproject]. To determine
trust, the user *must* make a trust decision about [pypa/sampleproject].

This trust decision can have a time dimension: a user might decide to trust
[pypa/sampleproject] because it was the first identity seen for the
`sampleproject` name on PyPI. Then, if a new release of `sampleproject` is
attested by a new identity ("`pypa/evil-sampleproject`") or has
no attestation at all, the user can *observe the difference automatically* and
begin to remediate it.

### Trusted Publishing

Because attestations are tied to Trusted Publisher identities, all
of the considerations in [Trusted Publishers - Security Model and Considerations]
apply to attestations as well.

In general: while more secure and misuse-resistant than a password or long-lived
API token, Trusted Publishing and attestations are **not** a substitute
for essential security practices like limiting who can trigger your publishing
workflows.

### "Keyless" signing with Sigstore

!!! tip

    The issuance aspects of "keyless" signing are documented in more detail
    in Fulcio's [Certificate Issuing Overview].

PyPI's support for attestations is built around "keyless" (also known
as "identity-based") signing.

Instead of long-lived signing keys, a PyPI project is signed for by
an *identity* matching one of its [Trusted Publishers]. This identity
is *cryptographically bound* to a short-lived signing key via an
OpenID Connect (OIDC) operation similar to the one that Trusted Publishing uses,
but against [Sigstore] instead:

1. The Trusted Publishing/attesting actor (such as a GitHub Actions workflow)
   is issued an OIDC token by its identity provider.

2. This OIDC token is sent to Sigstore's public certificate authority (CA),
   [Fulcio], along with the public half of an ephemeral keypair.

    If the OIDC token is valid (i.e. is not expired and was issued by the
    identity provider that it claims), Fulcio responds with an X.509 signing
    certificate that binds the OIDC token's claims to the public key.

3. The attesting actor can now sign things with the private half of its
   ephemeral keypair. The ephemeral private key can be discarded
   after signing is complete, since the X.509 signing certificate permanently
   binds its public half to the identity used during verification.

This "keyless" approach represents a **tradeoff** between usability and trust:
unlike traditional long-lived signing keys, there is a *trusted party*
(Sigstore's Fulcio CA) that intermediates the binding between a signing
key and the identity associated with it. In exchange for this trusted party,
Sigstore enables misuse-resistant, short-lived signing keys bound to
verifiable identities.

This is similar to the tradeoff made in [HTTPS], where CAs serve as trusted
parties that bind a website's identity (its domain) to its public key.

Like the HTTPS ecosystem, Sigstore takes steps to reduce *unnecessary* trust
in the Fulcio CA:

* Sigstore operates a [Certificate Transparency] (CT) log, which can be
  monitored and audited to confirm that Fulcio does not issue certificates
  for a given identity except when given an authentic credential for that
  identity.

* Sigstore also operates [Rekor] as an "artifact transparency" log, effectively
  recording every signing event done with a Fulcio-issued certificate. Like
  the CT log, Rekor can be monitored and audited to confirm that a
  Fulcio-issued certificate does not sign

Put together, these transparency mechanisms attenuate the trust placed
in Fulcio by making Fulcio's integrity *cryptographically auditable and
verifiable*.

PyPI's attestations feature makes full use of these trust-reduction techniques:
attestations are not considered verified unless they include an inclusion proof
from Rekor, as well as an inclusion proof from Fulcio's CT log.

[Trusted Publishing]: /trusted-publishers/

[Sigstore's "keyless signing"]: https://docs.sigstore.dev/cosign/signing/overview/

[Trusted Publishers - Security Model and Considerations]: /trusted-publishers/security-model/

[Trusted Publishers]: /trusted-publishers/

[Sigstore]: https://docs.sigstore.dev/

[Fulcio]: https://docs.sigstore.dev/certificate_authority/overview/

[Certificate Issuing Overview]: https://docs.sigstore.dev/certificate_authority/certificate-issuing-overview/

[HTTPS]: https://en.wikipedia.org/wiki/HTTPS

[Certificate Transparency]: https://certificate.transparency.dev/

[Rekor]: https://docs.sigstore.dev/logging/overview/

[attested]: https://pypi.org/project/sampleproject/#sampleproject-4.0.0.tar.gz

[pypa/sampleproject]: https://github.com/pypa/sampleproject
