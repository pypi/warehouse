---
title: Security Model and Considerations
---

# Security model and considerations

## General considerations

PyPI's support for attestations is built on top of a combination
of [Trusted Publishing] and [Sigstore's "keyless signing"] ability.
See below for security considerations for each.

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
in Fulcio by making Fulcio's honesty *cryptographically auditable and
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
