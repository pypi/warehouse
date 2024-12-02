# Index API

This page documents PyPI's implementation of the
[PEP 503] (HTML) and [PEP 691] (JSON) index API.

[PEP 503]: https://peps.python.org/pep-0503/

[PEP 691]: https://peps.python.org/pep-0691/

!!! note

    The index API is sometimes called the "legacy API,"
    since it provides feature parity with PyPI's legacy codebase.

!!! note

    This API is available as both HTML and JSON.

    It is recommended that new integrations use the JSON version.

## Routes

### List all projects

Route: `GET /simple/`

Returns all of the projects that have been registered.

Response headers:

* `X-PyPI-Last-Serial` - The most recent serial ID number for any project.

Status codes:

* `200 OK` - no error

#### HTML

Example HTML request (default if no `Accept` header is passed):

```http
GET /simple/ HTTP/1.1
Host: pypi.org
Accept: application/vnd.pypi.simple.v1+html
```

??? note "Example HTML response"

    ```http
    HTTP/1.0 200 OK
    Content-Type: application/vnd.pypi.simple.v1+html
    X-PyPI-Last-Serial: 24888689

    <html>
      <head>
        <meta name="pypi:repository-version" content="1.1">
        <title>Simple index</title>
      </head>
      <body>
        <a href="/simple/0/">0</a>
        <a href="/simple/0-0/">0-._.-._.-._.-._.-._.-._.-0</a>
        <!-- More projects... -->
      </body>
    </html>
    ```

#### JSON

Example JSON request:

```http
GET /simple/ HTTP/1.1
Host: pypi.org
Accept: application/vnd.pypi.simple.v1+json
```

??? note "Example JSON response"

    ```http
    HTTP/1.1 200 OK
    Content-Type: application/vnd.pypi.simple.v1+json
    X-PyPI-Last-Serial: 24888689

    {
      "meta": {
        "_last-serial": 24888689,
        "api-version": "1.1"
      },
      "projects": [
        {
          "_last-serial": 3075854,
          "name": "0"
        },
        {
          "_last-serial": 1448421,
          "name": "0-._.-._.-._.-._.-._.-._.-0"
        },
        "More projects..."
      ]
    }
    ```

### Get distributions for project

Route: `GET /simple/<project>/`

Get all of the distribution download URLs for the `project`'s
available releases (wheels and source distributions). The project
is matched case-insensitively with the `_`, `-` and `.`
characters considered equal.  The links may optionally include a
hash using the URL fragment. This fragment is in the form of
`#<hashname>=<hexdigest>`. If present the downloaded file *MUST*
be verified against that hash value. Valid hash values are
`md5`, `sha1`, `sha224`, `sha256`, `sha384`, and
`sha512`.

If a PGP/GPG signature for a distribution file exists in PyPI, it
is available at the same URL as the file with `.asc` appended,
but a link to that signature is not provided in this list of
URLs. Therefore, once you have a wheel or sdist filename such as
`https://file.pythonhosted.org/.../foo-1.0.tar.gz`, you can
check for the existence of
`https://file.pythonhosted.org/.../foo-1.0.tar.gz.asc` with a
separate `GET` request.

Response headers:

* `X-PyPI-Last-Serial` - The most recent serial ID number for the project.

Status codes:

* `200 OK` - no error

#### HTML

Example HTML request (default if no `Accept` header is passed):

```http
GET /simple/beautifulsoup4/ HTTP/1.1
Host: pypi.org
Accept: application/vnd.pypi.simple.v1+html
```

??? note "Example HTML response"

    ```http
    HTTP/2 200 OK
    Content-Type: application/vnd.pypi.simple.v1+html
    Etag: "q4SqZutq1tfRDqhh3zQ4gQ"
    X-PyPI-Last-Serial: 2857110

    <!DOCTYPE html>
    <html>
      <head>
        <meta name="pypi:repository-version" content="1.1">
        <title>Links for beautifulsoup4</title>
      </head>
      <body>
        <h1>Links for beautifulsoup4</h1>
        <a href="https://files.pythonhosted.org/packages/6f/be/99dcf74d947cc1e7abef5d0c4572abcb479c33ef791d94453a8fd7987d8f/beautifulsoup4-4.0.1.tar.gz#sha256=dc6bc8e8851a1c590c8cc8f25915180fdcce116e268d1f37fa991d2686ea38de" >beautifulsoup4-4.0.1.tar.gz</a><br />
        <a href="https://files.pythonhosted.org/packages/a0/75/db36172ea767dd2f0c9817a99e24f7e9b79c2ce63eb2f8b867284cc60daf/beautifulsoup4-4.0.2.tar.gz#sha256=353792f8246a9551b232949fb14dce21d9b6ced9207bf9f4a69a4c4eb46c8127" >beautifulsoup4-4.0.2.tar.gz</a><br />
        <!-- ...More files... -->
        <a href="https://files.pythonhosted.org/packages/14/7e/e4313dad823c3a0751c99b9bc0182b1dd19aea164ce7445e9a70429b9e92/beautifulsoup4-4.13.0b2-py3-none-any.whl#sha256=7e05ad0b6c26108d9990e2235e8a9b4e2c03ead6f391ceb60347f8ebea6b80ba" data-requires-python="&gt;=3.6.0" data-dist-info-metadata="sha256=d0aa787c2b55e5b0b3aff66f137cf33341c5e781cb87b4dc184cbb25c7ac0ab5" data-core-metadata="sha256=d0aa787c2b55e5b0b3aff66f137cf33341c5e781cb87b4dc184cbb25c7ac0ab5">beautifulsoup4-4.13.0b2-py3-none-any.whl</a><br />
        <a href="https://files.pythonhosted.org/packages/81/bd/c97d94e2b96f03d1c50bc9de04130e014eda89322ba604923e0c251eb02e/beautifulsoup4-4.13.0b2.tar.gz#sha256=c684ddec071aa120819889aa9e8940f85c3f3cdaa08e23b9fa26510387897bd5" data-requires-python="&gt;=3.6.0" >beautifulsoup4-4.13.0b2.tar.gz</a><br />
      </body>
    </html>
    <!--SERIAL 22406780-->
    ```

#### JSON

Example JSON request:

```http
GET /simple/beautifulsoup4/ HTTP/1.1
Host: pypi.org
Accept: application/vnd.pypi.simple.v1+json
```

??? note "Example JSON response"

    ```http
    HTTP/2 200 OK
    Content-Type: application/vnd.pypi.simple.v1+json
    Etag: "hVGQAYl/eoNrx2H5FmPuXw"
    X-PyPI-Last-Serial: 22406780

    {
      "files": [
        {
          "core-metadata": false,
          "data-dist-info-metadata": false,
          "filename": "beautifulsoup4-4.0.1.tar.gz",
          "hashes": {
            "sha256": "dc6bc8e8851a1c590c8cc8f25915180fdcce116e268d1f37fa991d2686ea38de"
          },
          "requires-python": null,
          "size": 51024,
          "upload-time": "2014-01-21T05:35:05.558877Z",
          "url": "https://files.pythonhosted.org/packages/6f/be/99dcf74d947cc1e7abef5d0c4572abcb479c33ef791d94453a8fd7987d8f/beautifulsoup4-4.0.1.tar.gz",
          "yanked": false
        },
        {
          "core-metadata": false,
          "data-dist-info-metadata": false,
          "filename": "beautifulsoup4-4.0.2.tar.gz",
          "hashes": {
            "sha256": "353792f8246a9551b232949fb14dce21d9b6ced9207bf9f4a69a4c4eb46c8127"
          },
          "requires-python": null,
          "size": 51240,
          "upload-time": "2014-01-21T05:35:09.581933Z",
          "url": "https://files.pythonhosted.org/packages/a0/75/db36172ea767dd2f0c9817a99e24f7e9b79c2ce63eb2f8b867284cc60daf/beautifulsoup4-4.0.2.tar.gz",
          "yanked": false
        },
        "...More files...",
        {
          "core-metadata": {
            "sha256": "524392d64a088e56a4232f50d6edb208dc03105394652acb72c6d5fa64c89f3e"
          },
          "data-dist-info-metadata": {
            "sha256": "524392d64a088e56a4232f50d6edb208dc03105394652acb72c6d5fa64c89f3e"
          },
          "filename": "beautifulsoup4-4.12.3-py3-none-any.whl",
          "hashes": {
            "sha256": "b80878c9f40111313e55da8ba20bdba06d8fa3969fc68304167741bbf9e082ed"
          },
          "requires-python": ">=3.6.0",
          "size": 147925,
          "upload-time": "2024-01-17T16:53:12.779164Z",
          "url": "https://files.pythonhosted.org/packages/b1/fe/e8c672695b37eecc5cbf43e1d0638d88d66ba3a44c4d321c796f4e59167f/beautifulsoup4-4.12.3-py3-none-any.whl",
          "yanked": false
        },
        {
          "core-metadata": false,
          "data-dist-info-metadata": false,
          "filename": "beautifulsoup4-4.12.3.tar.gz",
          "hashes": {
            "sha256": "74e3d1928edc070d21748185c46e3fb33490f22f52a3addee9aee0f4f7781051"
          },
          "requires-python": ">=3.6.0",
          "size": 581181,
          "upload-time": "2024-01-17T16:53:17.902970Z",
          "url": "https://files.pythonhosted.org/packages/b3/ca/824b1195773ce6166d388573fc106ce56d4a805bd7427b624e063596ec58/beautifulsoup4-4.12.3.tar.gz",
          "yanked": false
        },
        {
          "core-metadata": {
            "sha256": "d0aa787c2b55e5b0b3aff66f137cf33341c5e781cb87b4dc184cbb25c7ac0ab5"
          },
          "data-dist-info-metadata": {
            "sha256": "d0aa787c2b55e5b0b3aff66f137cf33341c5e781cb87b4dc184cbb25c7ac0ab5"
          },
          "filename": "beautifulsoup4-4.13.0b2-py3-none-any.whl",
          "hashes": {
            "sha256": "7e05ad0b6c26108d9990e2235e8a9b4e2c03ead6f391ceb60347f8ebea6b80ba"
          },
          "requires-python": ">=3.6.0",
          "size": 179607,
          "upload-time": "2024-03-20T13:00:33.355932Z",
          "url": "https://files.pythonhosted.org/packages/14/7e/e4313dad823c3a0751c99b9bc0182b1dd19aea164ce7445e9a70429b9e92/beautifulsoup4-4.13.0b2-py3-none-any.whl",
          "yanked": false
        },
        {
          "core-metadata": false,
          "data-dist-info-metadata": false,
          "filename": "beautifulsoup4-4.13.0b2.tar.gz",
          "hashes": {
            "sha256": "c684ddec071aa120819889aa9e8940f85c3f3cdaa08e23b9fa26510387897bd5"
          },
          "requires-python": ">=3.6.0",
          "size": 550258,
          "upload-time": "2024-03-20T13:00:31.245327Z",
          "url": "https://files.pythonhosted.org/packages/81/bd/c97d94e2b96f03d1c50bc9de04130e014eda89322ba604923e0c251eb02e/beautifulsoup4-4.13.0b2.tar.gz",
          "yanked": false
        }
      ],
      "meta": {
        "_last-serial": 22406780,
        "api-version": "1.1"
      },
      "name": "beautifulsoup4",
      "versions": [
        "4.0.1",
        "4.0.2",
        "...More versions...",
        "4.12.3",
        "4.13.0b2"
      ]
    }
    ```
