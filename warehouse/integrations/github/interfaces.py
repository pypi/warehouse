class IGitHubTokenScanningPayloadVerifyService(Interface):
    def verify(*, payload, key_id, signature):
        """
        GitHub scans tokens for us and sends us a payload with published
        tokens. Before we analyze the payload, we need to check the signature.

        Checking the signature may involve the following steps:
        - Checking the signature key id against GitHub's meta API
        - Dowloading the signature key from that API
        - Cryptographically check the signature with the signature key and the payload

        It's possible that implementers do only some of those steps.

        Return True if the signature is valid for this payload using GitHub's key.
        """
