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
# https://bitbucket.org/zzzeek/sqlalchemy/wiki/UsageRecipes/WindowedRangeQuery

from sqlalchemy import and_, func, text


def column_windows(session, column, windowsize):
    """
    Return a series of WHERE clauses against a given column that break it into
    windows.

    Result is an iterable of tuples, consisting of ((start, end), whereclause),
    where (start, end) are the ids.

    Requires a database that supports window functions, i.e. Postgresql,
    SQL Server, Oracle.

    Enhance this yourself !  Add a "where" argument so that windows of just a
    subset of rows can be computed.
    """

    def int_for_range(start_id, end_id):
        if end_id:
            return and_(column >= start_id, column < end_id)
        else:
            return column >= start_id

    q = session.query(
        column, func.row_number().over(order_by=column).label("rownum")
    ).from_self(column)

    if windowsize > 1:
        q = q.filter(text("rownum %% %d=1" % windowsize))

    intervals = [row[0] for row in q]

    while intervals:
        start = intervals.pop(0)
        if intervals:
            end = intervals[0]
        else:
            end = None

        yield int_for_range(start, end)


def windowed_query(q, column, windowsize):
    """
    Break a Query into windows on a given column.
    """

    for whereclause in column_windows(q.session, column, windowsize):
        for row in q.filter(whereclause).order_by(column):
            yield row
