# SPDX-License-Identifier: Apache-2.0

"""
Warehouse Flake8 Local Checkers

This module contains custom Flake8 checkers that are used to enforce
Warehouse-specific style rules.
"""

import ast
from pathlib import Path
from textwrap import dedent  # for testing

from collections.abc import Generator
from typing import Any

WH001_msg = "WH001 Prefer `urllib3.util.parse_url` over `urllib.parse.urlparse`"
WH002_msg = (
    "WH002 Prefer `sqlalchemy.orm.relationship(back_populates=...)` "
    "over `sqlalchemy.orm.relationship(backref=...)`"
)
WH003_msg = "WH003 `@view_config.renderer` configured template file not found"


class WarehouseVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.errors: list[tuple[int, int, str]] = []
        self.filename = filename

    def check_for_backref(self, node) -> None:
        def _check_keywords(keywords: list[ast.keyword]) -> None:
            for kw in keywords:
                if kw.arg == "backref":
                    self.errors.append((kw.lineno, kw.col_offset, WH002_msg))

        # Nodes can be either Attribute or Name, and depending on the type
        # of node, the value.func can be either an attr or an id.
        # TODO: This is aching for a better way to do this.
        if isinstance(node.value, ast.Call):
            if (
                isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "relationship"
                and isinstance(node.value.keywords, list)
            ):
                _check_keywords(node.value.keywords)
            elif (
                isinstance(node.value.func, ast.Name)
                and node.value.func.id == "relationship"
                and isinstance(node.value.keywords, list)
            ):
                _check_keywords(node.value.keywords)

    def template_exists(self, template_name: str) -> bool:
        repo_root = Path(__file__).parent.parent.parent

        # If the template name is a full package path, check if it exists
        # in the package's templates directory.
        if ":" in template_name:
            pkg, resource = template_name.split(":", 1)
            pkg_path = repo_root.joinpath(*pkg.split("."))
            resource_path = pkg_path / resource
            return resource_path.is_file()

        settings = {}
        # TODO: Replace with actual configuration retrieval if it makes sense
        # Get Jinja2 search paths from warehouse config
        # settings = configure().get_settings()
        search_paths = settings.get("jinja2.searchpath", [])
        # If not set, fallback to default templates path
        if not search_paths:
            search_paths = [
                str(repo_root / "warehouse" / "templates"),
                str(repo_root / "warehouse" / "admin" / "templates"),
            ]
        for path in search_paths:
            if Path(path, template_name).is_file():
                return True
        return False

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id == "urlparse":
            self.errors.append((node.lineno, node.col_offset, WH001_msg))

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if (
            node.attr == "urlparse"
            and isinstance(node.value, ast.Attribute)
            and node.value.value.id == "urllib"
        ):
            self.errors.append((node.lineno, node.col_offset, WH001_msg))

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        self.check_for_backref(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        self.check_for_backref(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and getattr(decorator.func, "id", None) == "view_config"
            ):
                for kw in decorator.keywords:
                    if (
                        kw.arg == "renderer"
                        and isinstance(kw.value, ast.Constant)
                        # TODO: Is there a "string-that-looks-like-a-filename"?
                        and kw.value.value not in ["json", "xmlrpc", "string"]
                    ):
                        if not self.template_exists(kw.value.value):
                            self.errors.append(
                                (kw.value.lineno, kw.value.col_offset, WH003_msg)
                            )
        self.generic_visit(node)


class WarehouseCheck:
    def __init__(self, tree: ast.AST, filename: str) -> None:
        self.tree = tree
        self.filename = filename

    def run(self) -> Generator[tuple[int, int, str, type[Any]]]:
        visitor = WarehouseVisitor(self.filename)
        visitor.visit(self.tree)

        for e in visitor.errors:
            yield *e, type(self)


# Testing
def test_wh003_renderer_template_not_found():
    # Simulate a Python file with a @view_config decorator and a non-existent template
    code = dedent(
        """
    from pyramid.view import view_config

    @view_config(renderer="non_existent_template.html")
    def my_view(request):
        pass
    """
    )
    tree = ast.parse(code)
    visitor = WarehouseVisitor(filename="test_file.py")
    visitor.visit(tree)

    # Assert that the WH003 error is raised
    assert len(visitor.errors) == 1
    assert visitor.errors[0][2] == WH003_msg


def test_wh003_renderer_template_in_package_path():
    code = dedent(
        """
    from pyramid.view import view_config

    @view_config(renderer="warehouse.admin:templates/admin/dashboard.html")
    def my_view(request):
        pass
    """
    )
    tree = ast.parse(code)
    visitor = WarehouseVisitor(filename="test_file.py")
    visitor.visit(tree)

    # Assert that no WH003 error is raised
    assert len(visitor.errors) == 0


if __name__ == "__main__":
    test_wh003_renderer_template_not_found()
    test_wh003_renderer_template_in_package_path()
    print("Test passed!")
