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

from warehouse.tuf.interfaces import IKeyService, IRepositoryService

TOPLEVEL_ROLES = ["root", "snapshot", "targets", "timestamp"]
BINS_ROLE = "bins"
BIN_N_ROLE = "bin-n"


def includeme(config):
    config.add_settings(
        {
            "tuf.keytype": "ed25519",
            "tuf.keyid_hash_algorithm": "sha512",
            "tuf.consistent_snapshot": True,
            "tuf.root.threshold": 1,
            "tuf.snapshot.threshold": 1,
            "tuf.targets.threshold": 1,
            "tuf.timestamp.threshold": 1,
            "tuf.bins.threshold": 1,
            "tuf.bin-n.threshold": 1,
            "tuf.bin-n.count": 16384,
            "tuf.spec_version": "1.0.0",
        }
    )

    key_service_class = config.maybe_dotted(config.registry.settings["tuf.key_backend"])
    config.register_service_factory(key_service_class.create_service, IKeyService)

    repo_service_class = config.maybe_dotted(config.registry.settings["tuf.repo_backend"])
    config.register_service_factory(repo_service_class.create_service, IRepositoryService)
