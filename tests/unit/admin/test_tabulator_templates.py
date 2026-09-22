# SPDX-License-Identifier: Apache-2.0

"""The escaping rule the declarative admin tables rest on.

Tabulator reads a server-rendered cell as innerHTML and, with the `html`
formatter these tables default to, writes it back the same way. The group
headings and the responsive-collapse block do that whatever the formatter is,
so every cell of a `data-tabulator` table has to be Jinja-autoescaped output.

Nothing in the rendering path can tell the difference, so the rule is checked
here: the first `|safe` added to one of these tables would be script execution
in an authenticated admin session.
"""

import pathlib
import re

import pytest

import warehouse.admin

_TEMPLATES = pathlib.Path(warehouse.admin.__file__).parent / "templates" / "admin"

# A <table data-tabulator ...> and everything up to its </table>.
_TABLE = re.compile(
    r"<table[^>]*\bdata-tabulator\b.*?</table>", re.DOTALL | re.IGNORECASE
)

# Anything that hands Jinja markup it will not escape.
_UNESCAPED = re.compile(r"\|\s*safe\b|\bMarkup\(|{%\s*autoescape\s+false")


def _tables():
    for path in sorted(_TEMPLATES.rglob("*.html")):
        source = path.read_text()
        for match in _TABLE.finditer(source):
            yield pytest.param(
                match.group(0),
                id=f"{path.parent.name}/{path.name}:"
                f"{source.count(chr(10), 0, match.start()) + 1}",
            )


@pytest.mark.parametrize("table", list(_tables()))
def test_declarative_table_cells_stay_escaped(table):
    assert not _UNESCAPED.search(table)
