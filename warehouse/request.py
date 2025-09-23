# SPDX-License-Identifier: Apache-2.0

import hashlib
import hmac
import secrets


def _create_nonce(request):
    """Generate a cryptographically secure random nonce for the request."""
    return secrets.token_urlsafe(32)


def _create_hashed_domains(request):
    """Create a list of hashed allowed domains using the request nonce as salt."""
    allowed_domains = request.registry.settings.get("warehouse.allowed_domains", [])

    if not allowed_domains:
        return ""

    hashed_domains = []
    nonce_bytes = request.nonce.encode("utf-8")

    for domain in allowed_domains:
        # Use HMAC with the nonce as the key and domain as the message
        domain_bytes = domain.encode("utf-8")
        hashed = hmac.new(nonce_bytes, domain_bytes, hashlib.sha256).hexdigest()
        hashed_domains.append(hashed)

    return ",".join(hashed_domains)


def includeme(config):
    # Add a nonce to every request
    config.add_request_method(_create_nonce, name="nonce", reify=True)

    # Add hashed domains to every request
    config.add_request_method(_create_hashed_domains, name="hashed_domains", reify=True)
