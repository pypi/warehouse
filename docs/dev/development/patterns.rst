Patterns
********

Dependency management
=====================

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

You can manually upgrade a specific dependency with::

    make deps_upgrade_project P={project_name}

For instance, to upgrade boto3::

    make deps_upgrade_project P=boto3

To upgrade all dependencies, you can use::

    make deps_upgrade_all

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
=============== ============================================

To add a new dependency:

1. Add the project name to the appropriate ``.in`` file
2. From the repositories root directory, recompile the dependencies for each modified ``.in`` file::

    make requirements/{file}.txt

3. Commit the changes

Removing existing dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Only top-level dependencies should be removed. The process is similar to the
process for adding new dependencies:

1. Remove the project name from the appropriate ``.in`` file
2. From the repositories root directory, recompile the dependencies for each modified ``.in`` file::

    make requirements/{file}.txt

3. Commit the changes

Returning vs Raising HTTP Exceptions
====================================

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

Implementing new services
=========================

Warehouse uses services to provide pluggable functionalities within the codebase. They are implemented using
`pyramid-services`_. After being registered, services are accessible using the ``find_service`` method of the
``request`` object.

When adding new services to ``warehouse``, the following checklist serves as a comprehensive guideline to ensure
you stay on track.

Adding a new service
~~~~~~~~~~~~~~~~~~~~~

1. Create an Interface for the service. The interface serves as the baseline of the new service (design by
   contract pattern) and details all methods and attributes shared by the different service implementations.

   Warehouse uses `zope.interface`_ to define interfaces. The interfaces are usually declared in a file named
   ``interfaces.py`` within the relevant component, such as ``packaging/interfaces.py``.

2. Create the new service. The service must define all methods and attributes declared in the interface.
   This implementation contains the core logic of the service features. Additionally, services may add
   further methods that are not required on all implementations of the interface.

3. (Optional) Create other implementations of the interface. For instance, many services in ``warehouse``
   also provide a ``NullService`` version used for development. These Null implementations only
   provide basic functionalities without verifications and reduce the need for stubs in tests.
   When implementing a warning for using the service, subclass the exception from
   ``warehouse.utils.exceptions.DevelopmentModeWarning`` to minimize warnings in the test logs.

   Any new implementation must implement the complete interface, including all its methods and attributes.

4. Implement each service creation method. If the Service is simple enough, use a class method in
   your service implementation (usually named ``create_service``). For more complex cases, implement
   a ``ServiceFactory`` class, responsible to create the service instance.

5. Register the service. The new service(s) must be registered to be available in the request object.

   - If you have multiple services, create a new setting (in ``warehouse/config.py``) to select
     which backend to use.

   - Add a default value for the setting in ``dev/environment`` for the development environment.

   - Use the setting value in the ``includeme`` function to instantiate the appropriate service.

   - Register your service factory. This registration must be in the service module's ``includeme``
     function for Pyramid to detect it and use the service factory created at the previous step.

6. (Optional) Add the new module to the ``warehouse/config.py``. If the new service is defined in a
   new module, add the new module within the warehouse ``configure`` function. This enrollment
   ensures Pyramid can detect it.

Using the service
~~~~~~~~~~~~~~~~~

To use a service, query it using ``request.find_service()`` with the service interface. This
method will return an instance of the service correctly selected based on the context and environment.

Example (from `packaging/utils.py`_):

.. code-block:: python

   storage = request.find_service(ISimpleStorage)


Testing the service
~~~~~~~~~~~~~~~~~~~

Like the rest of the ``warehouse`` codebase, the new service requires tests. Below are some
recommended practices for performing appropriate tests.

Testing the service itself
^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Implement a ``test_includeme`` function to test the service registration.
2. Test each service implementation individually to meet ``warehouse`` 100% test coverage.

   - Write a ``Test<ServiceName>`` class and implement ``test_interface_matches`` function (the exact name is irrelevant) to verify that the service implementation matches the interface definition using the ``verifyClass`` function from zope.

   - Write appropriate test functions for the different methods.

3. Register the new service using its interface in ``tests/conftests.py``.
4. (Optional) Modify ``tests/unit/test_config.py`` to check:

   - If you have multiple services, that the new setting exists.
   - That the module registration works if your service is part of a new module.

5. (Optional) Depending on the needs, create a pytest fixture that returns the NullService
   and register it in the pyramid_services fixture.

Testing the service usage
^^^^^^^^^^^^^^^^^^^^^^^^^

Except in the service tests, avoid mocking the service behavior and use the ``NullService``
instead.

Example
~~~~~~~

The following `Pull Request`_ can serve as a baseline as it implements all these steps.


.. |pip-tools| replace:: ``pip-tools``
.. _pip-tools: https://pypi.org/project/pip-tools/
.. _`packaging/utils.py`: https://github.com/pypi/warehouse/blob/a36ae299d043bb4a770d6fd0f4e73b8e99dd6461/warehouse/packaging/utils.py#L122
.. _Dependabot pull requests: https://github.com/pypi/warehouse/pulls?q=is%3Apr+is%3Aopen+label%3Adependencies
.. _`pyramid-services`: https://github.com/mmerickel/pyramid_services
.. _`zope.interface`: https://zopeinterface.readthedocs.io/
.. _pull request: https://github.com/pypi/warehouse/pull/16546
