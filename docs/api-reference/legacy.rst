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

    :resheader X-PyPI-Last-Serial: The most recent serial id number for any
                                   project.
    :statuscode 200: no error


.. http:get:: /simple/<project>/

    Get all of the URLS for the ``project``. The project is matched case
    insensitively with the ``_`` and ``-`` characters considered equal.
    The links may optionally include a hash using the url fragment. This
    fragment is in the form of ``#<hashname>=<hexdigest>``. If present
    the downloaded file *MUST* be verified against that hash value. Valid
    hash values are ``md5``, ``sha1``, ``sha224``, ``sha256``, ``sha384``, and
    ``sha512``.

    **Example request**:

    .. code:: http

        GET /simple/beautifulsoup/ HTTP/1.1
        Host: pypi.org
        Accept: text/html

    **Example response**:

    .. code:: http

        HTTP/1.0 200 OK
        Content-Type: text/html; charset=utf-8
        X-PyPI-Last-Serial: 761270

        <!DOCTYPE html>
        <html>
          <head>
            <title>Links for BeautifulSoup</title>
          </head>
          <body>
            <h1>Links for BeautifulSoup</h1>
            <a href="https://files.pythonhosted.org/packages/33/fe/15326560884f20d792d3ffc7fe8f639aab88647c9d46509a240d9bfbb6b1/BeautifulSoup-3.2.0.tar.gz#sha256=0dc52d07516c1665c9dd9f0a390a7a054bfb7b147a50b2866fb116b8909dfd37">BeautifulSoup-3.2.0.tar.gz</a><br/>
            <a href="https://files.pythonhosted.org/packages/1e/ee/295988deca1a5a7accd783d0dfe14524867e31abb05b6c0eeceee49c759d/BeautifulSoup-3.2.1.tar.gz#sha256=6a8cb4401111e011b579c8c52a51cdab970041cc543814bbd9577a4529fe1cdb">BeautifulSoup-3.2.1.tar.gz</a><br/>
            </body>
        </html>
        <!--SERIAL 761270-->

    :resheader X-PyPI-Last-Serial: The most recent serial id number for the
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
<http://twine.readthedocs.io/>`_ and `distutils
<https://docs.python.org/3.6/distutils/packageindex.html#the-upload-command>`_
use to `upload distributions to PyPI
<https://packaging.python.org/tutorials/distributing-packages/>`_.
