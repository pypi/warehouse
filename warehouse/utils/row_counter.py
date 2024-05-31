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

from celery.schedules import crontab
from sqlalchemy import BigInteger, func, sql
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db, tasks
from warehouse.accounts.models import User
from warehouse.packaging.models import File, Project, Release

COUNTED_TABLES = [User, Project, Release, File]


class RowCount(db.Model):
    __tablename__ = "row_counts"

    table_name: Mapped[str] = mapped_column(unique=True)
    count: Mapped[int] = mapped_column(BigInteger, server_default=sql.text("0"))


@tasks.task(ignore_result=True, acks_late=True)
def compute_row_counts(request):
    for table in COUNTED_TABLES:
        request.db.execute(
            sql.update(RowCount)
            .where(RowCount.table_name == table.__tablename__)
            .values(count=sql.select(func.count()).select_from(table).scalar_subquery())
        )


def includeme(config):
    # Setup our Row Counts to be maintained on a 5 minute interval
    config.add_periodic_task(crontab(minute="*/5"), compute_row_counts)
