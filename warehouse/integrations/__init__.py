# SPDX-License-Identifier: Apache-2.0

import base64
import time

from typing import cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA, EllipticCurvePublicKey
from cryptography.hazmat.primitives.hashes import SHA256


class InvalidPayloadSignatureError(Exception):
    def __init__(self, message, reason):
        self.reason = reason
        super().__init__(message)


class CacheMissError(Exception):
    pass


class PublicKeysCache:
    """
    In-memory time-based cache. store with set(), retrieve with get().
    """

    def __init__(self, cache_time):
        self.cached_at = 0
        self.cache = None
        self.cache_time = cache_time

    def get(self, now):
        if not self.cache:
            raise CacheMissError

        if self.cached_at + self.cache_time < now:
            self.cache = None
            raise CacheMissError

        return self.cache

    def set(self, now, value):
        self.cached_at = now
        self.cache = value


class PayloadVerifier:
    def __init__(
        self,
        metrics,
        public_keys_cache: PublicKeysCache,
    ):
        self._metrics = metrics
        self._public_keys_cache = public_keys_cache

    @property
    def metric_name(self):
        raise NotImplementedError

    def verify(self, *, payload, key_id, signature):
        public_key = None
        try:
            public_keys = self._get_cached_public_keys()
            public_key = self._check_public_key(public_keys=public_keys, key_id=key_id)
        except (CacheMissError, InvalidPayloadSignatureError):
            # No cache or outdated cache, it's ok, we'll do a real call.
            # Just record a metric so that we can know if all calls lead to
            # cache misses
            self._metrics.increment(f"warehouse.{self.metric_name}.auth.cache.miss")
        else:
            self._metrics.increment(f"warehouse.{self.metric_name}.auth.cache.hit")

        try:
            if not public_key:
                pubkey_api_data = self.retrieve_public_key_payload()
                public_keys = self.extract_public_keys(pubkey_api_data)
                public_key = self._check_public_key(
                    public_keys=public_keys, key_id=key_id
                )

            self._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
        except InvalidPayloadSignatureError as exc:
            self._metrics.increment(
                f"warehouse.{self.metric_name}.auth.error.{exc.reason}"
            )
            return False

        self._metrics.increment(f"warehouse.{self.metric_name}.auth.success")
        return True

    def retrieve_public_key_payload(self):
        raise NotImplementedError

    def extract_public_keys(self, unused):
        raise NotImplementedError

    def _get_cached_public_keys(self):
        return self._public_keys_cache.get(now=time.time())

    def _check_public_key(self, public_keys, key_id):
        for record in public_keys:
            if record["key_id"] == key_id:
                return record["key"]

        raise InvalidPayloadSignatureError(
            f"Key {key_id} not found in public keys", reason="wrong_key_id"
        )

    def _check_signature(self, payload, public_key, signature):
        try:
            loaded_public_key = serialization.load_pem_public_key(
                data=public_key.encode("utf-8"), backend=default_backend()
            )
            # Use Type Narrowing to confirm the loaded_public_key is the correct type
            loaded_public_key = cast(EllipticCurvePublicKey, loaded_public_key)
            loaded_public_key.verify(
                signature=base64.b64decode(signature),
                data=payload,
                # This validates the ECDSA and SHA256 part
                signature_algorithm=ECDSA(algorithm=SHA256()),
            )
        except InvalidSignature as exc:
            raise InvalidPayloadSignatureError(
                "Invalid signature", "invalid_signature"
            ) from exc
        except Exception as exc:
            # Maybe the key is not a valid ECDSA key, maybe the data is not properly
            # padded, etc. So many things can go wrong...
            raise InvalidPayloadSignatureError(
                "Invalid cryptographic values", "invalid_crypto"
            ) from exc
