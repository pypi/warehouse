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


@task(bind=True, ignore_result=True, acks_late=True)
def add_target(task, request, file):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with utils.RepoLock(r):
        fileinfo = utils.make_fileinfo(file)
        repository = utils.open_repository(request)

        repository.add_target_to_bin(file.path, fileinfo=fileinfo)

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
