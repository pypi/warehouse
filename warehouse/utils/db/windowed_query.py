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
# updated from, with minor tweaks:
# https://github.com/sqlalchemy/sqlalchemy/discussions/7948#discussioncomment-2597083


def windowed_query(s, q, column, windowsize):
    """Break a Query into chunks on a given column."""

    q = q.add_columns(column).order_by(column)
    last_id = None

    while True:
        subq = q
        if last_id is not None:
            subq = subq.filter(column > last_id)
        chunk = s.execute(subq.limit(windowsize)).all()
        if not chunk:
            break
        last_id = chunk[-1][-1]
        yield from chunk
