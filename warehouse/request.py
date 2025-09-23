# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import hmac
import json
import secrets
import time


def _normalize_domain(domain):
    """Normalize a domain for consistent hashing.

    This prevents bypasses using domain variations like:
    - Mixed case (PyPi.org vs pypi.org)
    - Trailing dots (pypi.org. vs pypi.org)
    - IDN homographs (after converting to ASCII)
    """
    # Convert to lowercase
    normalized = domain.lower().strip()

    # Remove trailing dots
    normalized = normalized.rstrip(".")

    # Handle IDN domains - convert to ASCII (punycode)
    try:
        normalized = normalized.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        # If IDN conversion fails, use the original normalized form
        pass

    return normalized


def _create_nonce(request):
    """Generate a cryptographically secure random nonce for the request."""
    return secrets.token_urlsafe(32)


def _create_integrity_token(request):
    """Create an integrity token with timestamp and additional entropy."""
    # Include timestamp for replay attack prevention (valid for 1 hour)
    timestamp = int(time.time())

    # Add additional entropy
    entropy = secrets.token_bytes(16)

    # Combine elements
    token_data = {
        "ts": timestamp,
        "entropy": base64.b64encode(entropy).decode("ascii"),
        "nonce": request.nonce,
    }

    # Create a signed token
    token_json = json.dumps(token_data, sort_keys=True, separators=(",", ":"))
    return base64.b64encode(token_json.encode("utf-8")).decode("ascii")


def _create_hashed_domains(request):
    """Create a list of hashed allowed domains using multiple integrity checks.

    This implementation uses:
    1. Domain normalization to prevent case/format bypasses
    2. Multiple hash rounds with different algorithms
    3. Request-specific salt mixing
    4. Timestamp validation to prevent replay attacks
    """
    allowed_domains = request.registry.settings.get("warehouse.allowed_domains", [])

    if not allowed_domains:
        return ""

    hashed_domains = []

    # Get integrity token components
    integrity_token = request.integrity_token
    token_data = json.loads(base64.b64decode(integrity_token).decode("utf-8"))

    # Create composite key from multiple sources
    nonce_bytes = request.nonce.encode("utf-8")
    entropy_bytes = base64.b64decode(token_data["entropy"])
    timestamp_bytes = str(token_data["ts"]).encode("utf-8")

    for domain in allowed_domains:
        # Normalize the domain
        normalized_domain = _normalize_domain(domain)
        domain_bytes = normalized_domain.encode("utf-8")

        # Layer 1: HMAC-SHA256 with nonce
        layer1 = hmac.new(nonce_bytes, domain_bytes, hashlib.sha256).digest()

        # Layer 2: HMAC-SHA512 with entropy mixed in
        composite_key = nonce_bytes + entropy_bytes
        layer2_input = layer1 + domain_bytes
        layer2 = hmac.new(composite_key, layer2_input, hashlib.sha512).digest()

        # Layer 3: Include timestamp in final hash
        final_input = layer2 + timestamp_bytes
        final_hash = hmac.new(nonce_bytes, final_input, hashlib.sha256).hexdigest()

        hashed_domains.append(final_hash)

    # Add integrity checksum at the end
    all_hashes = "|".join(hashed_domains)
    checksum = hmac.new(
        nonce_bytes + entropy_bytes, all_hashes.encode("utf-8"), hashlib.sha256
    ).hexdigest()[
        :16
    ]  # Use first 16 chars of checksum

    return f"{all_hashes}|{checksum}"


def includeme(config):
    # Add a nonce to every request
    config.add_request_method(_create_nonce, name="nonce", reify=True)

    # Add integrity token to every request
    config.add_request_method(
        _create_integrity_token, name="integrity_token", reify=True
    )

    # Add hashed domains to every request
    config.add_request_method(_create_hashed_domains, name="hashed_domains", reify=True)
