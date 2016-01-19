Patterns
========

.. contents::
    :local:


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
