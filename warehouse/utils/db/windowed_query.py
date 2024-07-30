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

# Taken from "Theatrum Chemicum" at
# https://github.com/sqlalchemy/sqlalchemy/wiki/RangeQuery-and-WindowedRangeQuery

from __future__ import annotations

import typing

from collections.abc import Iterator
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

if typing.TYPE_CHECKING:
    from sqlalchemy import Result, Select, SQLColumnExpression


def column_windows(
    session: Session,
    stmt: Select[Any],
    column: SQLColumnExpression[Any],
    windowsize: int,
) -> Iterator[SQLColumnExpression[bool]]:
    """Return a series of WHERE clauses against
    a given column that break it into windows.

    Result is an iterable of WHERE clauses that are packaged with
    the individual ranges to select from.

    Requires a database that supports window functions.
    """
    rownum = func.row_number().over(order_by=column).label("rownum")

    subq = stmt.add_columns(rownum).subquery()
    subq_column = list(subq.columns)[-1]

    target_column = subq.corresponding_column(column)  # type: ignore
    new_stmt = select(target_column)  # type: ignore

    if windowsize > 1:
        new_stmt = new_stmt.filter(subq_column % windowsize == 1)

    intervals = list(session.scalars(new_stmt))

    # yield out WHERE clauses for each range
    while intervals:
        start = intervals.pop(0)
        if intervals:
            yield and_(column >= start, column < intervals[0])
        else:
            yield column >= start


def windowed_query(
    session: Session,
    stmt: Select[Any],
    column: SQLColumnExpression[Any],
    windowsize: int,
) -> Iterator[Result[Any]]:
    """Given a Session and Select() object, organize and execute the statement
    such that it is invoked for ordered chunks of the total result.   yield
    out individual Result objects for each chunk.
    """
    for whereclause in column_windows(session, stmt, column, windowsize):
        yield session.execute(stmt.filter(whereclause).order_by(column))
