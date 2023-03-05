Providing Remote Access For User Testing
========================================

.. contents::
    :local:

Motivation
----------

From time to time you may want to provide access to a development instance
of warehouse running locally with someone else. A common usecase is testing
or reviewing a new feature without merging changes or deploying software.

Tools
-----

Historically `ngrok <https://ngrok.com>`_ has been used and is what warehouse
maintainers are familiar with, but
`alternatives <https://github.com/anderspitman/awesome-tunneling>`_
exist, if there's a tool that you use that suits, please open a pull request
to add docs here!

ngrok (simple)
--------------

Follow `ngrok's quickstart guide <https://ngrok.com/docs/guides/quickstart>`_
to get ngrok installed, authenticated, and familiarize yourself.

After installation, you can start the warehouse services locally with
``make serve``, then in a separate terminal window run ``ngrok http 80``.

Share the URL from ``ngrok``'s output with anyone you want.

.. warning::
    The most notable thing that does not work with the simple ``ngrok http 80``
    command above is external images such as gravatar profile pictures, sponsor
    logos, and images included in project descriptions

    Follow the advanced guide if you need these features to work when sharing
    local environment

ngrok (advanced)
----------------

.. warning::
    This requires a paid ngrok.com account

Create an ngrok configuration file such as

.. code-block::

    authtoken: deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
    tunnels:
      warehouse-local:
        addr: 80
        proto: http
        subdomain: pypi-preview
      camo-local:
        addr: 9000
        proto: http
        subdomain: camo-preview

Update ``dev/enviroment.local`` with the camo URL

.. code-block::

    $ cat dev/environment.local
    CAMO_URL=https://camo-preview.ngrok.io/

Start and stop your local instances via docker-compose to pick up the
configuration change.

Camo will now work!
