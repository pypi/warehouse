class GitHubPublicKeyMetaAPIError(InvalidTokenLeakRequest):
    pass


@implementer(IGitHubTokenScanningPayloadVerifyService)
class GitHubTokenScanningPayloadVerifyService:
    """
    Checks payload signature using:
    - `requests` for HTTP calls
    - `cryptography` for signature verification
    """

    def __init__(self, *, session, metrics, api_token=None):
        self._metrics = metrics
        self._session = session
        self._api_token = api_token

    @classmethod
    def create_service(cls, context, request):
        return cls(
            session=request.http,
            metrics=request.find_service(IMetricsService, context=context),
            api_token=request.registry.settings["github.token"],
        )

    def verify(self, *, payload, key_id, signature):

        try:
            pubkey_api_data = self._retrieve_public_key_payload()
            public_keys = self._extract_public_keys(pubkey_api_data)
            public_key = self._check_public_key(
                github_public_keys=public_keys, key_id=key_id
            )
            self._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
        except InvalidTokenLeakRequest as exc:
            self._metrics.increment(
                f"warehouse.token_leak.github.auth.error.{exc.reason}"
            )
            return False

        self._metrics.increment("warehouse.token_leak.github.auth.success")
        return True

    def _get_headers(self):
        if self._api_token:
            return {"Authorization": f"token {self._api_token}"}
        return {}

    def _retrieve_public_key_payload(self):
        # TODO: cache ?

        token_scanning_pubkey_api_url = (
            "https://api.github.com/meta/public_keys/token_scanning"
        )
        headers = self._get_headers()
        try:
            response = self._session.get(token_scanning_pubkey_api_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            # TODO Log, including status code and body
            raise GitHubPublicKeyMetaAPIError(
                f"Invalid response code {response.status_code}: {response.text[:100]}",
                f"public_key_api.status.{response.status_code}",
            ) from exc
        except json.JSONDecodeError as exc:
            raise GitHubPublicKeyMetaAPIError(
                f"Non-JSON response received: {response.text[:100]}",
                "public_key_api.invalid_json",
            ) from exc
        except requests.RequestException as exc:
            # TODO Log
            raise GitHubPublicKeyMetaAPIError(
                "Could not connect to GitHub", "public_key_api.network_error"
            ) from exc

    def _extract_public_keys(self, pubkey_api_data):
        if not isinstance(pubkey_api_data, dict):
            raise GitHubPublicKeyMetaAPIError(
                f"Payload is not a dict but: {str(pubkey_api_data)[:100]}",
                "public_key_api.format_error",
            )
        try:
            public_keys = pubkey_api_data["public_keys"]
        except KeyError:
            raise GitHubPublicKeyMetaAPIError(
                "Payload misses 'public_keys' attribute", "public_key_api.format_error"
            )

        if not isinstance(public_keys, list):
            raise GitHubPublicKeyMetaAPIError(
                "Payload 'public_keys' attribute is not a list",
                "public_key_api.format_error",
            )

        expected_attributes = {"key", "key_identifier"}
        for public_key in public_keys:

            if not isinstance(public_key, dict):
                raise GitHubPublicKeyMetaAPIError(
                    f"Key is not a dict but: {public_key}",
                    "public_key_api.format_error",
                )

            attributes = set(public_key)
            if not expected_attributes <= attributes:
                raise GitHubPublicKeyMetaAPIError(
                    "Missing attribute in key: "
                    f"{sorted(expected_attributes - attributes)}",
                    "public_key_api.format_error",
                )

            yield {"key": public_key["key"], "key_id": public_key["key_identifier"]}

        return public_keys

    def _check_public_key(self, github_public_keys, key_id):
        for record in github_public_keys:
            if record["key_id"] == key_id:
                return record["key"]

        raise InvalidTokenLeakRequest(
            f"Key {key_id} not found in github public keys", reason="wrong_key_id"
        )

    def _check_signature(self, payload, public_key, signature):
        try:
            loaded_public_key = serialization.load_pem_public_key(
                data=public_key.encode("utf-8"), backend=default_backend()
            )
            loaded_public_key.verify(
                signature=base64.b64decode(signature),
                data=payload.encode("utf-8"),
                # This validates the ECDSA and SHA256 part
                signature_algorithm=ECDSA(algorithm=SHA256()),
            )
        except InvalidSignature as exc:
            raise InvalidTokenLeakRequest(
                "Invalid signature", "invalid_signature"
            ) from exc
        except Exception as exc:
            # Maybe the key is not a valid ECDSA key, maybe the data is not properly
            # padded, etc. So many things can go wrong...
            raise InvalidTokenLeakRequest(
                "Invalid cryptographic values", "invalid_crypto"
            ) from exc


@implementer(IGitHubTokenScanningPayloadVerifyService)
class NullGitHubTokenScanningPayloadVerifyService:
    """
    Doesn't really check anything, avoids HTTP calls, always validate
    """

    def verify(self, *, payload, key_id, signature):
        return True
