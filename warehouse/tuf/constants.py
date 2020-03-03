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

import enum


@enum.unique
class Role(enum.Enum):
    ROOT: str = "root"
    SNAPSHOT: str = "snapshot"
    TARGETS: str = "targets"
    TIMESTAMP: str = "timestamp"
    BINS: str = "bins"
    BIN_N: str = "bin-n"


TOPLEVEL_ROLES = [
    Role.ROOT.value,
    Role.SNAPSHOT.value,
    Role.TARGETS.value,
    Role.TIMESTAMP.value,
]

HASH_ALGORITHM = "blake2b"

TUF_REPO_LOCK = "tuf-repo"

BIN_N_COUNT = 16384
