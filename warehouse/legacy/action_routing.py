# SPDX-License-Identifier: Apache-2.0


class PyPIActionPredicate:
    def __init__(self, action: str, info):
        self.action_name = action

    def text(self) -> str:
        return f"pypi_action = {self.action_name}"

    phash = text

    def __call__(self, context, request) -> bool:
        return self.action_name == request.params.get(":action", None)


def add_pypi_action_route(config, name, action, **kwargs):
    config.add_route(name, "/pypi", pypi_action=action, **kwargs)


def add_pypi_action_redirect(config, action, target, **kwargs):
    config.add_redirect("/pypi", target, pypi_action=action, **kwargs)


def includeme(config):
    config.add_route_predicate("pypi_action", PyPIActionPredicate)
    config.add_directive(
        "add_pypi_action_route", add_pypi_action_route, action_wrap=False
    )
    config.add_directive(
        "add_pypi_action_redirect", add_pypi_action_redirect, action_wrap=False
    )
