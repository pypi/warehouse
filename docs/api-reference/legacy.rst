Legacy API
==========


Simple Project API
------------------

.. http:get:: /simple/

    All of the projects that have been registered. All responses *MUST* have
    a ``<meta name="api-version" value="2" />`` tag where the only valid
    value is ``2``.

    **Example request**:

    .. code:: http

        GET /simple/ HTTP/1.1
        Host: pypi.python.org
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
            <meta name="api-version" value="2" />
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
    insensitively with the ``_`` and ``-`` characters considered equal. All
    responses *MUST* have a ``<meta name="api-version" value="2" />`` tag where
    the only valid value is ``2``. The URLs returned by this API are classified
    by their ``rel`` attribute.

    ============ =============================================================
      rel name                               value
    ============ =============================================================
    internal     Projects hosted by this repository, *MUST* be a direct
                 project link.
    homepage     The homepage of the project, *MAY* be a direct project link
                 and *MAY* be fetched and processed for more direct project
                 links.
    download     The download url for the project, *MAY* be a direct project
                 link and *MAY* be fetched and processed for more direct
                 project links.
    ext-homepage The homepage of the project, *MUST* not be fetched to look
                 for more projects, *MAY* be a direct link.
    ext-download The download url for the project, **MUST** not be fetched to
                 look for more projects but *MAY* be a direct project link.
    external     An externally hosted url, *MUST* not be fetched to look for
                 more projects but *MAY* be a direct project link.
    ============ =============================================================

    The links may optionally include a hash using the url fragment. This
    fragment is in the form of ``#<hashname>=<hexdigest>``. If present
    the downloaded file *MUST* be verified against that hash value. Valid
    hash values are ``md5``, ``sha1``, ``sha224``, ``sha256``, ``sha384``, and
    ``sha512``.

    **Example request**:

    .. code:: http

        GET /simple/warehouse/ HTTP/1.1
        Host: pypi.python.org
        Accept: text/html

    **Example response**:

    .. code:: http

        HTTP/1.0 200 OK
        Content-Type: text/html; charset=utf-8
        X-PyPI-Last-Serial: 867465

        <!DOCTYPE html>
        <html>
          <head>
            <title>Links for warehouse</title>
            <meta name="api-version" value="2" />
          </head>
          <body>
            <h1>Links for warehouse</h1>
            <a rel="internal" href="../../packages/source/w/warehouse/warehouse-13.9.1.tar.gz#md5=f7f467ab87637b4ba25e462696dfc3b4">warehouse-13.9.1.tar.gz</a>
            <a rel="internal" href="../../packages/3.3/w/warehouse/warehouse-13.9.1-py2.py3-none-any.whl#md5=d105995d0b3dc91f938c308a23426689">warehouse-13.9.1-py2.py3-none-any.whl</a>
            <a rel="internal" href="../../packages/source/w/warehouse/warehouse-13.9.0.tar.gz#md5=b39322c1e6af3dda210d75cf65a14f4c">warehouse-13.9.0.tar.gz</a>
            <a rel="internal" href="../../packages/3.3/w/warehouse/warehouse-13.9.0-py2.py3-none-any.whl#md5=8767c0ed961ee7bc9e5e157998cd2b40">warehouse-13.9.0-py2.py3-none-any.whl</a>
          </body>
        </html>

    :resheader X-PyPI-Last-Serial: The most recent serial id number for the
                                   project.
    :statuscode 200: no error
