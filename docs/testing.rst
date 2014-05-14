Testing
=======

Database Access
---------------

Warehouse includes generators for creating data to test against. These
generators can be found in ``tests.lib.db``. Using them is pretty simple, you
select which generator you want and either call ``FooFactory.create()`` or
``FooFactory.build()`` depending on if you want the factory to also create
the database row or not.

Example:

.. code-block:: python3

    from .lib.db import ProjectFactory, ReleaseFactory, ReleaseFileFactory

    def test_index(dbapp):
        project1 = ProjectFactory.create(engine=dbapp.engine)
        project2 = ProjectFactory.create(engine=dbapp.engine)

        resp = index(dbapp, object())

        assert resp.response.context["project_count"] == 2

The database generators are built using the
`factory_boy <https://factoryboy.readthedocs.org>`_ library, and their
documentation can be used to read how you can use the various types of fields,
including "fuzzy" fields which will dynamically generate values at runtime.


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
