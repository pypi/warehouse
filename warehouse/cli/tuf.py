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

import click

from tuf import repository_tool

from warehouse.cli import warehouse
from warehouse.tuf import BIN_N_ROLE, BINS_ROLE, TOPLEVEL_ROLES, utils

# TUF_REPO = "warehouse/tuf/dist"


def _make_backsigned_fileinfo_from_file(file):
    return utils.make_fileinfo(file, custom={"backsigned": True})


def _key_service_for_role(config, role):
    key_service_class = config.maybe_dotted(config.registry.settings["tuf.key_backend"])
    return key_service_class.create_service(role, config)


def _repository_service(config):
    repo_service_class = config.maybe_dotted(
        config.registry.settings["tuf.repo_backend"]
    )
    return repo_service_class.create_service(config)


@warehouse.group()  # pragma: no-branch
def tuf():
    """
    Manage Warehouse's TUF state.
    """


# TODO: Need subcommands for:
# 1. creating the world (totally new TUF repo, including root)
# 2. updating the root metadata (including revocations?)
# 3. removing stale metadata


@tuf.command()
@click.pass_obj
@click.option("--name", "name_", help="The name of the TUF role for this keypair")
@click.option("--path", "path_", help="The basename of the Ed25519 keypair to generate")
def keypair(config, name_, path_):
    repository_tool.generate_and_write_ed25519_keypair(
        path_, password=config.registry.settings[f"tuf.{name_}.secret"]
    )


@tuf.command()
@click.pass_obj
def new_repo(config):
    """
    Initialize the TUF repository from scratch, including a brand new root.
    """

    repository = repository_tool.create_new_repository(
        config.registry.settings["tuf.repo.path"]
    )

    for role in TOPLEVEL_ROLES:
        key_service = _key_service_for_role(config, role)

        role_obj = getattr(repository, role)
        role_obj.threshold = config.registry.settings[f"tuf.{role}.threshold"]

        pubkeys = key_service.get_pubkeys()
        privkeys = key_service.get_privkeys()
        if len(pubkeys) < role_obj.threshold or len(privkeys) < role_obj.threshold:
            raise click.ClickException(
                f"Unable to initialize TUF repo ({role} needs {role_obj.threshold} keys"
            )

        for pubkey in pubkeys:
            role_obj.add_verification_key(pubkey)

        for privkey in privkeys:
            role_obj.load_signing_key(privkey)

    repository.mark_dirty(TOPLEVEL_ROLES)
    repository.writeall(
        consistent_snapshot=config.registry.settings["tuf.consistent_snapshot"],
    )


@tuf.command()
@click.pass_obj
def build_targets(config):
    """
    Given an initialized (but empty) TUF repository, create the delegated
    targets role (bins) and its hashed bin delegations (each bin-n).
    """

    repo_service = _repository_service(config)
    repository = repo_service.load_repository()

    # Load signing keys. We do this upfront for the top-level roles.
    for role in ["snapshot", "targets", "timestamp"]:
        key_service = _key_service_for_role(config, role)
        role_obj = getattr(repository, role)

        [role_obj.load_signing_key(k) for k in key_service.get_privkeys()]

    bins_key_service = _key_service_for_role(config, BINS_ROLE)
    bin_n_key_service = _key_service_for_role(config, BIN_N_ROLE)

    # NOTE: TUF normally does delegations by path patterns (i.e., globs), but PyPI
    # doesn't store its uploads on the same logical host as the TUF repository.
    # The last parameter to `delegate` is a special sentinel for this.
    repository.targets.delegate(BINS_ROLE, bins_key_service.get_pubkeys(), [])
    for privkey in bins_key_service.get_privkeys():
        repository.targets(BINS_ROLE).load_signing_key(privkey)

    repository.targets(BINS_ROLE).delegate_hashed_bins(
        [], bin_n_key_service.get_pubkeys(), config.registry.settings["tuf.bin-n.count"]
    )

    dirty_roles = ["snapshot", "targets", "timestamp", BINS_ROLE]
    for idx in range(1, 2 ** 16, 4):
        low = f"{idx - 1:04x}"
        high = f"{idx + 2:04x}"
        dirty_roles.append(f"{low}-{high}")

    repository.mark_dirty(dirty_roles)
    repository.writeall(
        consistent_snapshot=config.registry.settings["tuf.consistent_snapshot"]
    )

    # Collect the "paths" for every PyPI package. These are packages already in
    # existence, so we'll add some additional data to their targets to
    # indicate that we're back-signing them.
    from warehouse.db import Session
    from warehouse.packaging.models import File

    db = Session(bind=config.registry["sqlalchemy.engine"])
    for file in db.query(File).all():
        fileinfo = _make_backsigned_fileinfo_from_file(file)
        repository.targets(BINS_ROLE).add_target_to_bin(
            file.path,
            number_of_bins=config.registry.settings["tuf.bin-n.count"],
            fileinfo=fileinfo,
        )

    repository.mark_dirty(dirty_roles)
    repository.writeall(
        consistent_snapshot=config.registry.settings["tuf.consistent_snapshot"],
        use_existing_fileinfo=True,
    )


@tuf.command()
@click.pass_obj
def new_root(config):
    """
    Create a new
    """
    pass
