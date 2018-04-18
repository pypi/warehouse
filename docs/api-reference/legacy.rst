Legacy API
==========

The "Legacy API" provides feature parity with `pypi-legacy`_, hence the term
"legacy".

.. _simple-api:

Simple Project API
------------------

The Simple API implements the HTML-based package index API as specified in `PEP
503`_.

.. http:get:: /simple/

    All of the projects that have been registered.

    **Example request**:

    .. code:: http

        GET /simple/ HTTP/1.1
        Host: pypi.org
        Accept: text/html

    **Example response**:

    .. code:: http

        HTTP/1.0 200 OK
        Content-Type: text/html; charset=utf-8
        X-PyPI-Last-Serial: 871501

        <!DOCTYPE html>
        <html>
          <head>
            <title>Simple Index</title>
          </head>
          <body>
            <!-- More projects... -->
            <a href="/simple/warehouse/">warehouse</a>
            <!-- ...More projects -->
          </body>
        </html>

    :resheader X-PyPI-Last-Serial: The most recent serial ID number for any
                                   project.
    :statuscode 200: no error


.. http:get:: /simple/<project>/

    Get all of the distribution download URLs for the ``project``'s
    available releases (wheels and source distributions). The project
    is matched case-insensitively with the ``_``, ``-`` and ``.``
    characters considered equal.  The links may optionally include a
    hash using the URL fragment. This fragment is in the form of
    ``#<hashname>=<hexdigest>``. If present the downloaded file *MUST*
    be verified against that hash value. Valid hash values are
    ``md5``, ``sha1``, ``sha224``, ``sha256``, ``sha384``, and
    ``sha512``.

    If a PGP/GPG signature for a distribution file exists in PyPI, it
    is available at the same URL as the file with ``.asc`` appended,
    but a link to that signature is not provided in this list of
    URLs. Therefore, once you have a wheel or sdist filename such as
    ``https://file.pythonhosted.org/.../foo-1.0.tar.gz``, you can
    check for the existence of
    ``https://file.pythonhosted.org/.../foo-1.0.tar.gz.asc`` with a
    separate ``GET`` request.

    **Example request**:

    .. code:: http

        GET /simple/beautifulsoup4/ HTTP/1.1
        Host: pypi.org
        Accept: text/html

    **Example response**:

    .. code:: http

        HTTP/2 200 OK
        Content-Type: text/html; charset=utf-8
        Etag: "q4SqZutq1tfRDqhh3zQ4gQ"
        X-PyPI-Last-Serial: 2857110

        <!DOCTYPE html>
        <html>
          <head>
            <title>Links for beautifulsoup4</title>
          </head>
          <body>
            <h1>Links for beautifulsoup4</h1>
            <a href="https://files.pythonhosted.org/packages/6f/be/99dcf74d947cc1e7abef5d0c4572abcb479c33ef791d94453a8fd7987d8f/beautifulsoup4-4.0.1.tar.gz#sha256=dc6bc8e8851a1c590c8cc8f25915180fdcce116e268d1f37fa991d2686ea38de">beautifulsoup4-4.0.1.tar.gz</a><br/>
            <a href="https://files.pythonhosted.org/packages/a0/75/db36172ea767dd2f0c9817a99e24f7e9b79c2ce63eb2f8b867284cc60daf/beautifulsoup4-4.0.2.tar.gz#sha256=353792f8246a9551b232949fb14dce21d9b6ced9207bf9f4a69a4c4eb46c8127">beautifulsoup4-4.0.2.tar.gz</a><br/>
            <!-- ...More files -->
            <a href="https://files.pythonhosted.org/packages/9e/d4/10f46e5cfac773e22707237bfcd51bbffeaf0a576b0a847ec7ab15bd7ace/beautifulsoup4-4.6.0-py3-none-any.whl#sha256=11a9a27b7d3bddc6d86f59fb76afb70e921a25ac2d6cc55b40d072bd68435a76">beautifulsoup4-4.6.0-py3-none-any.whl</a><br/>
            <a href="https://files.pythonhosted.org/packages/fa/8d/1d14391fdaed5abada4e0f63543fef49b8331a34ca60c88bd521bcf7f782/beautifulsoup4-4.6.0.tar.gz#sha256=808b6ac932dccb0a4126558f7dfdcf41710dd44a4ef497a0bb59a77f9f078e89">beautifulsoup4-4.6.0.tar.gz</a><br/>
            </body>
        </html>
        <!--SERIAL 2857110-->

    :resheader X-PyPI-Last-Serial: The most recent serial ID number for the
                                   project.
    :statuscode 200: no error


.. _`pypi-legacy`: https://pypi.python.org/
.. _`PEP 503`: https://www.python.org/dev/peps/pep-0503/

.. _upload-api-forklift:

Upload API
----------

The API endpoint served at `upload.pypi.org/legacy/
<https://upload.pypi.org/legacy/>`_ is Warehouse's emulation of the
legacy PyPI upload API. This is the endpoint that tools such as `twine
<https://twine.readthedocs.io/>`_ and `distutils
<https://docs.python.org/3.6/distutils/packageindex.html#the-upload-command>`_
use to `upload distributions to PyPI
<https://packaging.python.org/tutorials/distributing-packages/>`_.
