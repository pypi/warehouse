# SPDX-License-Identifier: Apache-2.0

"""
Warehouse Flake8 Local Checkers

This module contains custom Flake8 checkers that are used to enforce
Warehouse-specific style rules.
"""

import ast

from collections.abc import Generator
from typing import Any

WH001_msg = "WH001 Prefer `urllib3.util.parse_url` over `urllib.parse.urlparse`"
WH002_msg = (
    "WH002 Prefer `sqlalchemy.orm.relationship(back_populates=...)` "
    "over `sqlalchemy.orm.relationship(backref=...)`"
)


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


class WarehouseCheck:
    def __init__(self, tree: ast.AST, filename: str) -> None:
        self.tree = tree
        self.filename = filename

    def run(self) -> Generator[tuple[int, int, str, type[Any]]]:
        visitor = WarehouseVisitor(self.filename)
        visitor.visit(self.tree)

        for e in visitor.errors:
            yield *e, type(self)
