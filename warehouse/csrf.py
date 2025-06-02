# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid.viewderivers import INGRESS, csrf_view

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def require_method_view(view, info):
    require_methods = info.options.get("require_methods", SAFE_METHODS)
    explicit = bool(info.options.get("require_methods"))

    # Support @view_config(require_methods=False) to disable this view deriver.
    if not require_methods:
        return view

    def wrapped(context, request):
        # If the current request is using an unallowed method then we'll reject
        # it *UNLESS* it is an exception view, then we'll allow it again
        # *UNLESS* the exception view set an explicit require_methods itself.
        if request.method not in require_methods and (
            getattr(request, "exception", None) is None or explicit
        ):
            raise HTTPMethodNotAllowed(
                headers={"Allow": ", ".join(sorted(require_methods))}
            )

        return view(context, request)

    return wrapped


require_method_view.options = {"require_methods"}  # type: ignore


def includeme(config):
    # Turn on all of our CSRF checks by default.
    config.set_default_csrf_options(require_csrf=True)

    # We want to shuffle things around so that the csrf_view comes over the
    # secured_view because we do not want to access the ambient authority
    # provided by the session cookie without first checking to ensure that this
    # is not a cross-site request.
    config.add_view_deriver(csrf_view, under=INGRESS, over="secured_view")

    # We also want to add a view deriver that will ensure that only allowed
    # methods get called on particular views. This needs to happen prior to
    # the CSRF checks happening to prevent the CSRF checks from firing on
    # views that don't expect them to.
    config.add_view_deriver(require_method_view, under=INGRESS, over="csrf_view")
