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
    insensitively with the ``_`` and ``-`` characters considered equal. The URLs
    returned by this API are classified by their ``rel`` attribute.

    ============ =============================================================
      rel name                               value
    ============ =============================================================
    internal     Packages hosted by this repository, *MUST* be a direct package
                 link.
    homepage     The homepage of the project, *MAY* be a direct package link
                 and *MAY* be fetched and processed for more direct package
                 links.
    download     The download url for the project, *MAY* be a direct package
                 link and *MAY* be fetched and processed for more direct
                 package links.
    ext-homepage The homepage of the project, *MUST* not be fetched to look
                 for more packages, *MAY* be a direct link.
    ext-download The download url for the project, **MUST** not be fetched to
                 look for more packages but *MAY* be a direct package link.
    external     An externally hosted url, *MUST* not be fetched to look for
                 more packages but *MAY* be a direct package link.
    ============ =============================================================

    The links may optionally include a hash using the url fragment. This
    fragment is in the form of ``#<hashname>=<hexdigest>``. If present
    the downloaded file *MUST* be verified against that hash value. Valid
    hash values are ``md5``, ``sha1``, ``sha224``, ``sha256``, ``sha384``, and
    ``sha512``.

    **Example request**:

    .. code:: http

        GET /simple/warehouse/ HTTP/1.1
        Host: pypi.org
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

Here is a table with all the metadata fields PyPI accepts 
when uploading a package.

================= ================= =================================== =======================
  Metadata Spec      PyPI Field                  Description                 Example Value     
================= ================= =================================== =======================
Metadata-Version  metadata_version  Version of the file format.*        "2.1"
Name              name              The name of the distribution.*      "Identipy"
Version           version           The distribution's version number.* "1.0a2"
Summary           summary           A one-line summary of what the      "A module for
                                    distribution does.*                 identifying pies
                                                                        in pictures using
                                                                        image recognition."
Description       description       The distribution description.       "Using the module is as
                                    Can be written using plain text,    easy as calling
                                    reStructuredText, or                `identipy_image()`."
                                    Markdown markup.
Author            author            The name and optional contact info  "P. Baker"
                                    of the author.
Author-email      author_email      The email of the author.            "pbaker@example.com"
                                    It can contain multiple
                                    comma-separated e-mail addresses.
Maintainer        maintainer        The name and optional contact info  "Kate Smith"
                                    of the maintainer. This field is
                                    intended for use when the original
                                    author is not the main maintainer.
Maintainer-email  maintainer_email  The email of the maintainer.        "katesm@email.com"
                                    It can contain multiple
                                    comma-separated e-mail addresses.
License           license           The license covering the            "This software may only
                                    distribution where the license      be used after the user
                                    is not an option in the             has succesfully mailed
                                    "License" Trove classifiers.        the author a chocolate."
Keywords          keywords          A space-separated list of keywords  "pie image recognition"
Classifier        classifiers       A list of valid classifier values   ["Development Status :: 4 - Beta",
                                                                         "Environment :: Console (Text Based)"]
Platform          platform          A Platfrm specification as a list   ["ObscureUnix", "RareBSD"]
                                    of operating systems not listed in
                                    the "Operating System" Trove
                                    classifier.
Home-page         home_page         The url of the distribution home    "https://pypie.com"
                                    page
Download-URL      download_url      The url from which this version     "https://pypie.com/1.0"
                                    of the distribution can be
                                    downloaded

* required.