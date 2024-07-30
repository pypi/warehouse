Frontend
========

The Warehouse frontend is (as you might suspect) written in JavaScript with the
CSS handled by SCSS. It uses ``webpack`` to process these files and prepare them for
serving.

All of the static files are located in ``warehouse/static/`` and external
libraries are found in ``package.json``.

The static files are compiled and included in the
``warehouse:docker-compose-static`` Docker image.


Building
--------

Static files should be automatically built when ``make serve`` is
running; however, you can also manually run commands in the ``static``
container:

.. code-block:: console

    $ # install dependencies
    $ docker compose run --rm static npm install

    $ # start a build
    $ docker compose run --rm static npm run build


Building outside of Docker
--------------------------

    Note: building outside of Docker is **not recommended** as it may
    install platform-specific dependencies.

Install `NodeJS 20.x <https://nodejs.org/en/download/releases/>`_,
install the dependencies using ``npm install`` and then run ``npm run
build``.

If you're in a POSIX environment you may find
`NVM <https://github.com/nvm-sh/nvm>`_ useful to have multiple NodeJS
versions installed in your system.


Tests
-----

The JavaScript codebase includes tests that can be run via
``make static_tests``. This target will run the static tests in the Docker
environment but they may also be run locally using ``npm run test`` once NodeJS
and the dependencies are installed as described above.

JavaScript tests use the `Jest testing framework <https://jestjs.io/>`_
along with `jest-dom <https://github.com/testing-library/jest-dom>`_
for assertion helpers. We can invoke Jest directly specify a particular
test suite via ``node_modules/.bin/jest tests/frontend/<TEST_FILE>.js`` or
add any of the `Jest CLI options <https://jestjs.io/docs/cli>`_ .
All tests are located in the ``tests/frontend``.

`Stimulus <https://stimulusjs.org/>`_ controller tests leverage on Jest
including `JSDOM <https://github.com/jsdom/jsdom/>`_ allowing us to
inject the required HTML markup for Stimulus in a setup phase. After the
setup we must manually instantiate and start a Stimulus application and
then test the functionality by triggering events in DOM elements and
asserting on the effects. See existing tests the details on how to
accomplish this.

.. note:: This workflow may cause race conditions, in particular when testing
    code in the early lifecycle events of the controllers. The application or
    controller may not be ready by the time we reach the assertions causing
    false negatives on the tests. In these cases it's best to keep the HTML
    setup in a ``beforeEach`` block, even if it means repeating the setup on
    different ``describe`` scenarios. This will ensure the application and
    controllers are ready before the actual test is run.

Deploying
---------

When deploying changes to the frontend, to see the changes immediately it is
necessary to purge the cache.

Individual pages can be purged from the command line by issuing a ``XPURGE``
request, e.g.::

    curl -XPURGE https://pypi.org/the/page/to/purge

All HTML pages can be dropped from the cache by purging the ``all-html``
surrogate key via our CDN provider.

The entire cache can be purged by issuing a "Purge All" via our CDN provider.

Purging the cache is not usually necessary when making frontend changes, unless
it would be unacceptable for the site to simultaneously have an "old" version
of some pages, but the "new" version of others.


Browser Support
---------------

We aim to support all major browsers. We also support one-back,
and follow the ``defaults`` recommendation from ``browserslist``.

You can see the full list of supported browsers by running ``npx browserslist``
in the root of the project.

HTML Code Style
---------------

Warehouse follows the `Google HTML style guide
<https://google.github.io/styleguide/htmlcssguide.html>`_, which is
enforced via linting with `HTML Linter
<https://github.com/deezer/html-linter>`_.

Exceptions to these rules include:

- Protocols can be included in links - we prefer to include ``https`` protocols
- All HTML tags should be closed

We also allow both dashes and underscores in our class names, as we
follow the `Nicholas Gallagher variation
<https://nicolasgallagher.com/about-html-semantics-front-end-architecture/>`_
of the `BEM naming methodology <https://en.bem.info/>`_.

More information on how BEM works can be found in `this article from
CSS Wizardry
<https://csswizardry.com/2013/01/mindbemding-getting-your-head-round-bem-syntax/>`_.

When using ``target="_blank_"`` for a hyperlink (usually to an external site),
we should always set ``rel="noopener"``.


SCSS Style and Structure
------------------------

Warehouse follows the `Airbnb CSS/Sass style guide <https://github.com/airbnb/css>`_,
with the exception that JS hooks should be prefixed with ``-js`` rather
than ``js``.

Our SCSS codebase is structured according to the `ITCSS system
<https://www.creativebloq.com/web-design/manage-large-scale-web-projects-new-css-architecture-itcss-41514731>`_.
The principle of this system is to break SCSS code into layers and
import them into a main stylesheet in an order moving from generic to
specific. This tightly controls the cascade of styles.

The majority of the SCSS styles are found within the 'blocks' layer,
with each BEM block in its own file. All blocks are documented at the top of
the file to provide guidelines for use and modification.

One of these blocks provides code syntax highlighting, which can be tested with
reference project provided at `<http://localhost/project/pypi-code-highlighting-demo/>`_
when using development database. Source reStructuredText file is available
`here <https://github.com/evemorgen/pypi-code-highlighting-demo>`_.
