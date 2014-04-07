Cross Site Request Forgery
==========================

Warehouse provides ``warehouse.csrf`` which houses the CSRF protections that
warehouse itself has. All methods not designated as "safe" by RFC2616 have on
by default CSRF protection.


Usage
=====

Protecting or exempting a view from CSRF protection is done using a very
simple decorator solution:


.. code-block:: python

    from warehouse.csrf import csrf_protect, csrf_exempt

    # Protect a view from CSRF attacks
    @csrf_protect
    def my_view(app, request):
        return Response("Protected from CSRF!")

    # Exempty a view from CSRF attacks
    @csrf_exempt
    def my_other_view(app, request):
        return Response("Not protected from CSRF :(")


If a view is not decorated and it receives an unsafe request, it will always
fail CSRF protection. Warehouse requires that views explicitly opt into CSRF
protection because the use of CSRF is a strong indicator that there is cookie
specific content on the page (the CSRF token).

If you need to cycle the CSRF token for any reason (unlikely!) you can do so
like:

.. code-block:: python

    from warehouse.csrf import csrf_cycle
    from warehouse.sessions import uses_session

    @uses_session
    def my_cycle_view(app, request):
        # This view just continuously recycles the users CSRF token
        csrf_cycle(request.session)

        return Response("Recycled!")


Protection Methods
==================

Warehouse employs two different techniques for protecting against CSRF attacks,
the Origin based and the secret token based.


Origin Based
------------

Strictly verify that the Origin or Referer headers of any particular "unsafe"
request matches the expected origin for this service. In particular this check
will:

1. First, determine the origin of the request by attempting to use the
   Origin header if it exists, or falling back to the Referer header if it
   doesn't.
2. Secondly, determine the expected origin for this service first by
   attempting to use the Host header, and falling back to SERVER_NAME:PORT
   otherwise.
3. Finally verify that we have all of the required information, and that
   the origin of the request matches the expected origin for this service
   or fail otherwise.


Secret Token Based
------------------

Strictly verify that the request included a secure token that is only known
to the application. This token will be stored inside of the session and
should be included as part of any form or ajax request that the application
makes.
