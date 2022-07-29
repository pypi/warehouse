Token Scanning
==============

People make mistakes. Sometimes, they post their PyPI tokens publicly. Some
content managers run regexes to try and identify published secrets, and ideally
have them deactivated. PyPI has started integrating with such systems in order
to help secure packages.


How to recognize a PyPI secret
------------------------------

A PyPI API token is a string consisting of a prefix (``pypi``), a separator
(``-``) and a macaroon serialized with PyMacaroonv2, which means it's the
``base64`` of::

    \x02\x01\x08pypi.org\x02\x01b

Thanks to this, we know that a PyPI token is bound to start with::

    pypi-AgEIcHlwaS5vcmc[A-Za-z0-9-_]{70,}

A token can be arbitrary long because we may add arbitrary many caveats. For
more details on the token format, see `pypitoken
<https://pypitoken.readthedocs.io>`_.

GitHub Secret Scanning
----------------------

GitHub's Token scanning feature used to be called "Token Scanning" and is now
"Secret Scanning". You may find the 2 names. GitHub scans public commits with
the regex above (actually the limit to at least 130 characters long). For all
tokens identified within a "push" event, they send us reports in bulk. The
format is explained thouroughly in `their doc
<https://docs.github.com/en/developers/overview/secret-scanning-partner-program>`_ as well as
in the `warehouse implementation ticket
<https://github.com/pypi/warehouse/issues/6051>`_.

In short: they send us a cryptographically signed payload describing each
leaked token alongside with a public URL pointing to it.

How to test it manually
^^^^^^^^^^^^^^^^^^^^^^^

A fake github service is launched by Docker Compose. Head your browser to
``http://localhost:8964``. Create/reorder/... one ore more public keys, make
sure one key is marked as current, then write your payload, using the following
format:

.. code-block:: json

    [{
        "type": "pypi_api_token",
        "token": "pypi-...",
        "url": "https://example.com"
    }]

Send your payload. It sends it to your local Warhouse. If a match is found, you
should find that:

- the token you sent has disappeared from the user account page,
- 2 new security events have been sent: one for the token deletion, one for the
  notification email.

After you send the token, the page will reload, and you'll find the details of
the request at the bottom. If all went well, you should see a ``204`` ('No
Content').

Whether it worked or not, a bunch of metrics have been issued, you can see them
in the `notdatadog` container log.

GitLab Secret Detection
-----------------------

GitLab also has an equivalent mechanism, named "Secret Detection", not
implemented in Warehouse yet (see `#9280
<https://github.com/pypi/warehouse/issues/9280>`_).

PyPI token disclosure infrastructure
------------------------------------

The code is mainly in ``warehouse/integration/github``.
There are 3 main parts in handling a token disclosure report:

- The Web view, which is the top-level glue but does not implement the logic
- Vendor specific authenticity check & loading. In the case of GitHub, we check
  that the payload and the associated signature match with the public keys
  available in their meta-API
- (Supposedly-)Vendor-independent disclosure analysis:

    - Each token is processed individually in its own celery task
    - Token is analyzed, we check if its format is correct and if it
      corresponds to a macaroon we have in the DB
    - We don't check the signature. This is something that could change in the
      future but for now, we consider that if a token identifier leaked, even
      without a valid signature, it's enough to warrant deleting it.
    - If it's valid, we delete it, log a security event and send an email
      (which will spawn a second celery task)
