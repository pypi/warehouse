Testing
=======


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

        assert resp.template.name == "index.html"
        assert resp.context == {
            "project_count": 5,
            "download_count": 10,
            "recently_updated": [],
        }
