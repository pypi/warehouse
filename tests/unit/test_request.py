# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse import request


class TestCreateNonce:
    def test_generates_unique_nonces(self):
        """Test that each request gets a unique nonce."""
        req1 = pretend.stub()
        req2 = pretend.stub()

        nonce1 = request._create_nonce(req1)
        nonce2 = request._create_nonce(req2)

        # Nonces should be strings
        assert isinstance(nonce1, str)
        assert isinstance(nonce2, str)

        # Nonces should have reasonable length (base64url encoded 32 bytes)
        assert len(nonce1) >= 32
        assert len(nonce2) >= 32

        # Nonces should be unique
        assert nonce1 != nonce2

    def test_nonce_is_url_safe(self):
        """Test that nonces are URL-safe."""
        req = pretend.stub()
        nonce = request._create_nonce(req)

        # Should only contain URL-safe characters
        # base64url uses A-Z, a-z, 0-9, -, _
        import re

        assert re.match(r"^[A-Za-z0-9_-]+$", nonce)


class TestCreateHashedDomains:
    def test_hashes_domains_with_nonce(self):
        """Test that domains are hashed using the nonce."""
        req = pretend.stub(
            nonce="test-nonce-123",
            registry=pretend.stub(
                settings={"warehouse.allowed_domains": ["pypi.org", "test.pypi.org"]}
            ),
        )

        hashed = request._create_hashed_domains(req)

        # Should return comma-separated list
        assert "," in hashed
        hashes = hashed.split(",")
        assert len(hashes) == 2

        # Each hash should be 64 chars (sha256 hex)
        for h in hashes:
            assert len(h) == 64
            assert all(c in "0123456789abcdef" for c in h)

        # Hashes should be different for different domains
        assert hashes[0] != hashes[1]

    def test_different_nonce_produces_different_hashes(self):
        """Test that different nonces produce different hashes for same domain."""
        req1 = pretend.stub(
            nonce="nonce-1",
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["pypi.org"]}),
        )
        req2 = pretend.stub(
            nonce="nonce-2",
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["pypi.org"]}),
        )

        hashed1 = request._create_hashed_domains(req1)
        hashed2 = request._create_hashed_domains(req2)

        assert hashed1 != hashed2

    def test_empty_domains_returns_empty_string(self):
        """Test that empty domain list returns empty string."""
        req = pretend.stub(
            nonce="test-nonce",
            registry=pretend.stub(settings={"warehouse.allowed_domains": []}),
        )

        hashed = request._create_hashed_domains(req)
        assert hashed == ""

    def test_no_domains_setting_returns_empty_string(self):
        """Test that missing domains setting returns empty string."""
        req = pretend.stub(nonce="test-nonce", registry=pretend.stub(settings={}))

        hashed = request._create_hashed_domains(req)
        assert hashed == ""
