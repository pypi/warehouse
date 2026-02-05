# SPDX-License-Identifier: Apache-2.0

from warehouse.config import configure

application = configure().make_wsgi_app()


def paste_app_factory(global_config, **settings):
    """PasteDeploy entry point for Pyramid p-scripts (ptweens, proutes, etc.).

    Pyramid's p-scripts require a PasteDeploy-compatible .ini file that
    references a paste.app_factory callable. Since Warehouse configures
    itself entirely through environment variables and the configure()
    function (rather than a .ini file), this thin wrapper bridges the two
    by accepting PasteDeploy's (global_config, **settings) signature and
    delegating to configure().

    See development.ini in the repository root and the Pyramid
    p-scripts documentation:
    https://docs.pylonsproject.org/projects/pyramid/en/latest/pscripts/
    """
    return configure(settings).make_wsgi_app()
