# Token Scanning

People make mistakes. Sometimes, they post their PyPI tokens publicly. Some
content managers run regexes to try and identify published secrets, and ideally
have them deactivated. PyPI has started integrating with such systems in order
to help secure packages.

User-facing documentation about this feature is available here:
<https://docs.pypi.org/api/secrets/>.

## How to test it manually

A fake token reporting service is launched by Docker Compose. Head your browser to
<http://localhost:8964>. Create/reorder/... one or more public keys, make
sure one key is marked as current, then write your payload, using the following
format:

```json
[{
    "type": "pypi_api_token",
    "token": "pypi-...",
    "url": "https://example.com"
}]
```

Send your payload. It sends it to your local Warehouse. If a match is found, you
should find that:

- the token you sent has disappeared from the user account page,
- 2 new security events have been sent: one for the token deletion, one for the
  notification email.

After you send the token, the page will reload, and you'll find the details of
the request at the bottom. If all went well, you should see a `204` ('No
Content').

Whether it worked or not, a bunch of metrics have been issued, you can see them
in the `notdatadog` container log.

## PyPI token disclosure infrastructure

The code is mainly in `warehouse/integrations/secrets/`.
There are 3 main parts in handling a token disclosure report:

- The Web view, which is the top-level glue but does not implement the logic
- Vendor specific authenticity check & loading. We check that the payload and
  the associated signature match with the public keys available in their
  meta-API
- Vendor-independent disclosure analysis:

    - Each token is processed individually in its own celery task
    - Token is analyzed, we check if its format is correct and if it
      corresponds to a macaroon we have in the DB
    - We don't check the signature. This is something that could change in the
      future but for now, we consider that if a token identifier leaked, even
      without a valid signature, it's enough to warrant deleting it.
    - If it's valid, we delete it, log a security event and send an email
      (which will spawn a second celery task)
