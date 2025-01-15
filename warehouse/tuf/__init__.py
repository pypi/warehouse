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

from warehouse import db
from warehouse.packaging.models import Project
from warehouse.tuf.interfaces import ITUFService
from warehouse.tuf.services import rstuf_factory
from warehouse.tuf.tasks import update_metadata


@db.listens_for(db.Session, "after_flush")
def update_metadata_for_project(config, session, flush_context):
    # We will start a task to update the metadata for each project that has been
    # deleted, yanked, unyanked, release deleted or release file deleted.
    if config.registry.settings.get("rstuf.api_url") is None:
        return

    for obj in session.new | session.dirty:
        if isinstance(obj, Project):
            config.task(update_metadata).delay(obj.id)


def includeme(config):
    config.register_service_factory(rstuf_factory, ITUFService)
