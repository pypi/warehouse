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

from tuf import repository_tool

from warehouse.tasks import task
from warehouse.tuf.interfaces import IKeyService

TOPLEVEL_ROLES = ["root", "snapshot", "targets", "timestamp"]


@task(bind=True, ignore_result=True, acks_late=True)
def new_repo(task, request):
    repository = repository_tool.create_new_repository("warehouse/tuf/dist")

    for role in TOPLEVEL_ROLES:
        key_service_factory = request.find_service_factory(IKeyService)
        key_service = key_service_factory(role, request)

        role_obj = getattr(repository, role)
        role_obj.threshold = request.registry.settings[f"tuf.{role}.threshold"]

        role_obj.add_verification_key(key_service.get_pubkey())
        role_obj.load_signing_key(key_service.get_privkey())

    repository.mark_dirty(TOPLEVEL_ROLES)
    for role in TOPLEVEL_ROLES:
        repository.write(
            role, consistent_snapshot=request.registry.settings["tuf.consistent_snapshot"]
        )
