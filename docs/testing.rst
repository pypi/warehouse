Testing
=======

Database Access
---------------

Various items, such as view functions, need to access the database in order
to properly test them. Often times these items require a set of state to exist
inside of the database in order to test properly or fully.

Warehouse includes a database fixture utility in order to aid in this. Fixtures
are defined in the file ``tests/db_fixtures.yaml``. This is a simple yaml file
that supports either single fixture definition, or collections.

.. code-block:: yaml

    # Single
    # This will be named "my-fixture-with-model"
    my-fixture-with-model:
      model: warehouse.packaging.tables:packages
      fields:
        name: my-package
        normalized_name: my-package

    # This will be named "my-fixture-without-model"
    my-fixture-without-model:
      fields:
        name: my-other-package
        normalized_name: my-other-package

    # Collections
    my-fixture-collection:
      model: warehouse.packaging.tables:releases

      # These will by the default fields
      fields:
        name: my-package

      objects:
        # This will be named "my-fixture-collection.release-1-0"
        release-1-0:
          version: "1.0"

        # This will be named "my-fixture-collection.release-2-0"
        release-2-0:
          version: "2.0"

Fixtures can be loaded into a test using the ``db_fixtures`` pytest fixture
directly, or using the ``tests.lib.db.db_fixtures`` decorator.

.. code-block:: python3

    # Using the ``db_fixtures`` pytest fixture directly
    def test_my_thing(db_fixtures):
        # Inserts the fixture into the database, and returns a dictionary of
        # fields
        thing1 = db_fixtures.install_fixture("my-fixture-with-models")

        # Doesn't insert the fixture into the database, but returns the
        # dictionary of fields
        thing2 = db_fixtures.get_fixture("my-fixture-collection.release-1-0")

        # Doesn't insert the fixture into the database, because it has no model
        # attribute, but will return the dictionary of fields
        thing3 = db_fixtures.install_fixture("my-fixture-without-model")

    # Using the ``tests.lib.db.db_fixtures`` decorator
    from tests.lib.db import db_fixtures

    @db_fixtures(
        "my-fixture-with-models",
        "my-fixture-collection.release-1-0",
        # This last one doesn't make much sense, since there is no model
        "my-fixture-without-model",
    )
    def test_my_other_thing(db_fixtures):  # The pytest fixture is still needed
        # All of the above fixtures will already have had install_fixture
        # called for them
        pass

The fixture system supports more than that, you can see the entire file format
at the `charlatan documentation <https://charlatan.readthedocs.org/en/latest/file-format.html>`_.



Template Rendering
------------------

The utility function ``warehouse.templates.render_response`` uses a special
``Response`` subclass which stores the context and template and lazily renders
the template when the response content is first accessed. This means that
testing view template rendering (or other functions that render templates) in
Warehouse can be as simple as:


.. code-block:: python3

    import pretend

    from warehouse.views

    def test_index(app):
        app.db = pretend.stub(
            packaging=pretend.stub(
                get_project_count=lambda: 5,
                get_download_count=lambda: 10,
                get_recently_updated=[],
            ),
        )

        resp = index(app, pretend.stub())

        assert resp.response.template.name == "index.html"
        assert resp.response.context == {
            "project_count": 5,
            "download_count": 10,
            "recently_updated": [],
        }
