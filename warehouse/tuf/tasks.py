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

import redis

from warehouse.tasks import task
from warehouse.tuf import utils
from warehouse.tuf.interfaces import IKeyService, IRepositoryService


@task(bind=True, ignore_result=True, acks_late=True)
def bump_timestamp(task, request):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with utils.RepoLock(r):
        repo_service = request.find_service(IRepositoryService)
        key_service = request.find_service(IKeyService)
        repository = repo_service.load_repository()

        for key in key_service.privkeys_for_role("timestamp"):
            repository.timestamp.load_signing_key(key)
        repository.mark_dirty(["timestamp"])
        repository.writeall(consistent_snapshot=True, use_existing_fileinfo=True)


@task(bind=True, ignore_result=True, acks_late=True)
def bump_snapshot(task, request):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with utils.RepoLock(r):
        pass


@task(bind=True, ignore_result=True, acks_late=True)
def bump_bins(task, request):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with utils.RepoLock(r):
        pass


@task(bind=True, ignore_result=True, acks_late=True)
def add_target(task, request, filepath, fileinfo):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with utils.RepoLock(r):
        # TODO(ww): How slow is this? Does it make more sense to pass the loaded
        # repository to the task?
        repo_service = request.find_service(IRepositoryService)
        key_service = request.find_service(IKeyService)
        repository = repo_service.load_repository()

        dirty_roles = ["snapshot", "timestamp"]
        for role in dirty_roles:
            role_obj = getattr(repository, role)
            [role_obj.load_signing_key(k) for k in key_service.privkeys_for_role(role)]

        # NOTE(ww): I think this should be targets("bins") instead of just targets,
        # but that fails with a missing delegated role under "bins". Possible
        # bug in load_repository?
        dirty_bin = repository.targets.add_target_to_bin(
            filepath,
            number_of_bins=request.registry.settings["tuf.bin-n.count"],
            fileinfo=fileinfo,
        )
        dirty_roles.append(dirty_bin)

        for k in key_service.privkeys_for_role("bin-n"):
            repository.targets(dirty_bin).load_signing_key(k)

        repository.mark_dirty(dirty_roles)
        repository.writeall(consistent_snapshot=True, use_existing_fileinfo=True)

    """
    First, it adds the new file path to the relevant bin-n metadata, increments its version number,
    signs it with the bin-n role key, and writes it to VERSION_NUMBER.bin-N.json.

    Then, it takes the most recent snapshot metadata, updates its bin-n metadata version numbers,
    increments its own version number, signs it with the snapshot role key, and writes it to
    VERSION_NUMBER.snapshot.json.

    And finally, the snapshot process takes the most recent timestamp metadata, updates its
    snapshot metadata hash and version number, increments its own version number, sets a new
    expiration time, signs it with the timestamp role key, and writes it to timestamp.json.
    """
