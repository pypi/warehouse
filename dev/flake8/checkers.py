# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Warehouse Flake8 Local Checkers

This module contains custom Flake8 checkers that are used to enforce
Warehouse-specific style rules.
"""

import ast

from collections.abc import Generator
from typing import Any

WH001_msg = "WH001 Prefer `urllib3.util.parse_url` over `urllib.parse.urlparse`"


class WarehouseVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.errors: list[tuple[int, int, str]] = []
        self.filename = filename

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


class WarehouseCheck:
    def __init__(self, tree: ast.AST, filename: str) -> None:
        self.tree = tree
        self.filename = filename

    def run(self) -> Generator[tuple[int, int, str, type[Any]], None, None]:
        visitor = WarehouseVisitor(self.filename)
        visitor.visit(self.tree)

        for e in visitor.errors:
            yield *e, type(self)
