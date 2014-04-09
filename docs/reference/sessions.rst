Sessions
========

Warehouse includes support for the standard cookie based session where the
session data is stored serialized via `MessagePack <http://msgpack.org/>`_ in
`Redis <http://redis.io/>`_.


Usage
-----

Using a session in a view is simple, simple decorate the view with the
``uses_session`` decorator and then access the session at ``request.session``.
Warehouse uses a decorator to enable session support to require an explicit
opt in to accessing that data. Typically when accessing the session the page
becomes cookie specific and cannot be as effectively cached.

The ``Session`` object is a dictionary like object which also supports
``Session().delete()`` and ``Session().cycle`` to delete the session or cycle
it to give it a new session identifier but preserve all the data respectively.


.. code-block:: python

    from warehouse.sessions import uses_session

    # Basic store some data in the session
    @uses_session
    def my_view(app, request):
        request.session["some data"] = "this is some data"
        return Response("stored some data")


    # Basic retrieve some data from the session
    @uses_session
    def my_other_view(app, request):
        return Response(request.session.get("some data", "No data :("))

    # Delete the session
    @uses_session
    def my_delete_view(app, request):
        request.session.delete()
        return Response("Oh No!")

    # Cycle the session
    @uses_session
    def my_cycle_view(app, request):
        request.session.cycle()
        return Response("Cycled!")

