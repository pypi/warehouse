Patterns
========

.. contents::
    :local:

Dependency management
---------------------

Warehouse's approach to dependency management can be summarized as follows:

- Separate requirements files for different environments (deploy, development,
  docs, linting, testing, etc.);
- All dependencies are pinned to precise versions, and include artifact hashes;
- Pinned requirements and subdependencies are compiled from ``.in`` files.

We install all dependencies with ``pip``, and we use |pip-tools|_ to compile
dependencies.

In practice, developers need to interact with our dependencies in three ways:

Upgrading existing dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dependencies are automatically upgraded via `Dependabot pull requests`_, and
occasionally merged by maintainers.

Adding new dependencies
~~~~~~~~~~~~~~~~~~~~~~~

Deciding to add a new dependency should be made carefully. Generally, we are
not opposed to adding more dependencies, however some effort should be made to
ensure that a given dependency:

- Is reasonably stable;
- Is currently maintained;
- Doesn't introduce a large amount of sub-dependencies.

All top-level dependencies are included in one or more ``.in`` files, which are
then compiled into ``.txt`` files with precise versions and artifact hashes.

When adding a new dependency, it's important to add it to the correct ``.in``
file:

=============== ============================================
File            Purpose
=============== ============================================
``deploy.in``   Required only to run in production
``docs.in``     For our documentation
``lint.in``     For linting our docs and codebase
``main.in``     Every dependency of our web service
``tests.in``    Required to run our tests
=============== ============================================

Dependencies that are either private or aren't deployed to production aren't
compiled:

=============== ============================================
File            Purpose
=============== ============================================
``dev.txt``     Various development dependencies
``ipython.txt`` Specific to using IPython as your shell
``theme.txt``   Private dependencies for our logos and theme
=============== ============================================

To add a new dependency:

1. Add the project name to the appropriate ``.in`` file
2. From the repositories root directory, recompile the dependencies for each modified ``.in`` file::

   $ pip-compile --allow-unsafe --generate-hashes --output-file=requirements/{file}.txt requirements/{file}.in

3. Commit the changes

Removing existing dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Only top-level dependencies should be removed. The process is similar to the
process for adding new dependencies:

1. Remove the project name from the appropriate ``.in`` file
2. From the repositories root directory, recompile the dependencies for each modified ``.in`` file::

   $ pip-compile --allow-unsafe --generate-hashes --output-file=requirements/{file}.txt requirements/{file}.in

3. Commit the changes

Returning vs Raising HTTP Exceptions
------------------------------------

Pyramid allows the various HTTP Exceptions to be either returned or raised,
and the difference between whether you return or raise them are subtle. The
differences between returning and raising a response are:

* Returning a response commits the transaction associated with the request,
  while raising rolls it back.
* Returning a response does not invoke the ``exec_view`` handler, while raising
  does.

The follow table shows what the *default* method should be for each type of
HTTP exception, this is only the default and judgement should be applied to
each situation.

========================= ==================================
Class                     Method
========================= ==================================
``HTTPSuccessful`` (2xx)  Return
``HTTPRedirection`` (3xx) Return
``HTTPClientError`` (4xx) Raise, except for ``HTTPNotFound`` which should be
                          return.
``HTTPServerError`` (5xx) Raise
========================= ==================================

.. |pip-tools| replace:: ``pip-tools``
.. _pip-tools: https://pypi.org/project/pip-tools/
.. _Dependabot pull requests: https://github.com/pypa/warehouse/pulls?q=is%3Apr+is%3Aopen+label%3Adependencies
