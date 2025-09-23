# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import hmac
import json
import time

import pretend
import pytest

from warehouse import request


class TestNormalizeDomain:
    @pytest.mark.parametrize(
        ("input_domain", "expected"),
        [
            # Lowercase normalization
            ("PyPi.ORG", "pypi.org"),
            ("TEST.PyPi.ORG", "test.pypi.org"),
            ("LOCALHOST", "localhost"),
            # Trailing dots removal
            ("pypi.org.", "pypi.org"),
            ("pypi.org...", "pypi.org"),
            ("localhost.", "localhost"),
            # Whitespace handling
            ("  pypi.org  ", "pypi.org"),
            ("\tpypi.org\n", "pypi.org"),
            ("  localhost  ", "localhost"),
            # Mixed normalizations
            ("  TEST.PyPi.ORG.  ", "test.pypi.org"),
            ("  LOCALHOST.  ", "localhost"),
            ("  127.0.0.1  ", "127.0.0.1"),
        ],
    )
    def test_domain_normalization(self, input_domain, expected):
        """Test that domains are properly normalized."""
        assert request._normalize_domain(input_domain) == expected

    def test_handles_idn_domains(self):
        """Test that IDN domains are converted to ASCII (punycode)."""
        # These are different Unicode characters that look similar
        assert request._normalize_domain("рyрі.org") != "pypi.org"  # Cyrillic chars
        # The result should be the punycode version
        assert request._normalize_domain("рyрі.org").startswith("xn--")

    def test_handles_invalid_idn_domains(self):
        """Test that invalid IDN domains fall back to normalized form."""
        # Test with invalid Unicode that can't be encoded to IDN
        # Using a string with invalid surrogate characters
        invalid_domain = "test\udcff.org"  # Contains an unpaired surrogate
        result = request._normalize_domain(invalid_domain)
        # Should return the normalized version without failing
        assert result == "test\udcff.org"

        # Test with a domain that causes encoding issues
        # Empty labels are not allowed in IDN
        invalid_domain2 = "test..org"
        result2 = request._normalize_domain(invalid_domain2)
        assert result2 == "test..org"


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


class TestCreateIntegrityToken:
    def test_creates_valid_token(self):
        """Test that integrity tokens are created with proper structure."""
        req = pretend.stub(nonce="test-nonce-123")

        token = request._create_integrity_token(req)

        # Should be base64 encoded
        assert isinstance(token, str)

        # Should be decodable
        decoded = base64.b64decode(token).decode("utf-8")
        token_data = json.loads(decoded)

        # Should have required fields
        assert "ts" in token_data
        assert "entropy" in token_data
        assert "nonce" in token_data

        # Timestamp should be recent
        current_time = int(time.time())
        assert abs(token_data["ts"] - current_time) < 5  # Within 5 seconds

        # Entropy should be base64 encoded
        entropy_bytes = base64.b64decode(token_data["entropy"])
        assert len(entropy_bytes) == 16

        # Nonce should match
        assert token_data["nonce"] == "test-nonce-123"

    def test_different_requests_get_different_tokens(self):
        """Test that different requests get different integrity tokens."""
        req1 = pretend.stub(nonce="nonce-1")
        req2 = pretend.stub(nonce="nonce-2")

        token1 = request._create_integrity_token(req1)
        token2 = request._create_integrity_token(req2)

        assert token1 != token2

        # Even with same nonce, entropy should differ
        req3 = pretend.stub(nonce="nonce-1")
        token3 = request._create_integrity_token(req3)

        assert token1 != token3


class TestCreateHashedDomains:
    def test_hashes_domains_with_enhanced_security(self):
        """Test that domains are hashed using multi-layer approach."""
        # Create a mock integrity token
        token_data = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"test-entropy-123").decode("ascii"),
            "nonce": "test-nonce-123",
        }
        integrity_token = base64.b64encode(
            json.dumps(token_data, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        req = pretend.stub(
            nonce="test-nonce-123",
            integrity_token=integrity_token,
            registry=pretend.stub(
                settings={"warehouse.allowed_domains": ["pypi.org", "test.pypi.org"]}
            ),
        )

        hashed = request._create_hashed_domains(req)

        # Should have pipe separators
        assert "|" in hashed
        parts = hashed.split("|")

        # Should have 2 domain hashes + 1 checksum
        assert len(parts) == 3

        # Each domain hash should be 64 chars (sha256 hex)
        for i in range(2):
            assert len(parts[i]) == 64
            assert all(c in "0123456789abcdef" for c in parts[i])

        # Checksum should be 16 chars
        assert len(parts[2]) == 16
        assert all(c in "0123456789abcdef" for c in parts[2])

        # Hashes should be different for different domains
        assert parts[0] != parts[1]

    def test_domain_normalization_applied(self):
        """Test that domain normalization is applied before hashing."""
        token_data = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"test-entropy-123").decode("ascii"),
            "nonce": "test-nonce-123",
        }
        integrity_token = base64.b64encode(
            json.dumps(token_data, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        # Two requests with different domain formats
        req1 = pretend.stub(
            nonce="test-nonce-123",
            integrity_token=integrity_token,
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["PyPi.ORG"]}),
        )

        req2 = pretend.stub(
            nonce="test-nonce-123",
            integrity_token=integrity_token,
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["pypi.org"]}),
        )

        hashed1 = request._create_hashed_domains(req1)
        hashed2 = request._create_hashed_domains(req2)

        # Should produce same hash despite different case
        assert hashed1 == hashed2

    def test_different_nonce_produces_different_hashes(self):
        """Test that different nonces produce different hashes for same domain."""
        token_data1 = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"entropy-1").decode("ascii"),
            "nonce": "nonce-1",
        }
        integrity_token1 = base64.b64encode(
            json.dumps(token_data1, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        token_data2 = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"entropy-2").decode("ascii"),
            "nonce": "nonce-2",
        }
        integrity_token2 = base64.b64encode(
            json.dumps(token_data2, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        req1 = pretend.stub(
            nonce="nonce-1",
            integrity_token=integrity_token1,
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["pypi.org"]}),
        )
        req2 = pretend.stub(
            nonce="nonce-2",
            integrity_token=integrity_token2,
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["pypi.org"]}),
        )

        hashed1 = request._create_hashed_domains(req1)
        hashed2 = request._create_hashed_domains(req2)

        assert hashed1 != hashed2

    def test_timestamp_affects_hash(self):
        """Test that timestamp changes affect the hash."""
        token_data1 = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"test-entropy").decode("ascii"),
            "nonce": "test-nonce",
        }

        token_data2 = {
            "ts": int(time.time()) + 100,  # 100 seconds later
            "entropy": base64.b64encode(b"test-entropy").decode("ascii"),
            "nonce": "test-nonce",
        }

        integrity_token1 = base64.b64encode(
            json.dumps(token_data1, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        integrity_token2 = base64.b64encode(
            json.dumps(token_data2, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        req1 = pretend.stub(
            nonce="test-nonce",
            integrity_token=integrity_token1,
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["pypi.org"]}),
        )

        req2 = pretend.stub(
            nonce="test-nonce",
            integrity_token=integrity_token2,
            registry=pretend.stub(settings={"warehouse.allowed_domains": ["pypi.org"]}),
        )

        hashed1 = request._create_hashed_domains(req1)
        hashed2 = request._create_hashed_domains(req2)

        # Hashes should be different due to different timestamps
        assert hashed1 != hashed2

    def test_empty_domains_returns_empty_string(self):
        """Test that empty domain list returns empty string."""
        token_data = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"test-entropy").decode("ascii"),
            "nonce": "test-nonce",
        }
        integrity_token = base64.b64encode(
            json.dumps(token_data, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        req = pretend.stub(
            nonce="test-nonce",
            integrity_token=integrity_token,
            registry=pretend.stub(settings={"warehouse.allowed_domains": []}),
        )

        hashed = request._create_hashed_domains(req)
        assert hashed == ""

    def test_no_domains_setting_returns_empty_string(self):
        """Test that missing domains setting returns empty string."""
        token_data = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"test-entropy").decode("ascii"),
            "nonce": "test-nonce",
        }
        integrity_token = base64.b64encode(
            json.dumps(token_data, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        req = pretend.stub(
            nonce="test-nonce",
            integrity_token=integrity_token,
            registry=pretend.stub(settings={}),
        )

        hashed = request._create_hashed_domains(req)
        assert hashed == ""

    def test_checksum_validates_integrity(self):
        """Test that the checksum properly validates the domain hashes."""
        token_data = {
            "ts": int(time.time()),
            "entropy": base64.b64encode(b"test-entropy-123").decode("ascii"),
            "nonce": "test-nonce-123",
        }
        integrity_token = base64.b64encode(
            json.dumps(token_data, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).decode("ascii")

        req = pretend.stub(
            nonce="test-nonce-123",
            integrity_token=integrity_token,
            registry=pretend.stub(
                settings={"warehouse.allowed_domains": ["pypi.org", "test.pypi.org"]}
            ),
        )

        hashed = request._create_hashed_domains(req)
        parts = hashed.split("|")

        # Verify checksum matches expected format
        checksum = parts[-1]
        assert len(checksum) == 16

        # If we change a hash, the checksum should be different
        # Recalculate checksum with modified hash
        modified_hashes = parts[:-1]
        modified_hashes[0] = "0" * 64  # Replace first hash with zeros

        nonce_bytes = b"test-nonce-123"
        entropy_bytes = b"test-entropy-123"

        all_hashes = "|".join(modified_hashes)
        new_checksum = hmac.new(
            nonce_bytes + entropy_bytes, all_hashes.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:16]

        # Checksums should be different
        assert new_checksum != checksum
