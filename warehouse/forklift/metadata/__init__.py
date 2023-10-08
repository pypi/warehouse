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

import os
import os.path
import zipfile

from packaging.metadata import Metadata
from packaging.utils import (
    parse_wheel_filename,
    canonicalize_name,
    canonicalize_version,
)
from webob.multidict import MultiDict


def parse(content: bytes | None, *, form_data: MultiDict) -> Metadata:
    pass


class InvalidArtifact(Exception):
    def __init__(self, reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reason = reason


def extract(path: os.PathLike) -> bytes | None:
    filename = os.path.basename(path)

    # TODO: Implement for sdists (requires Metadata 2.2)
    if filename.endswith(".whl"):
        name, version, _, _ = parse_wheel_filename(filename)
        version = canonicalize_version(version)

        with zipfile.ZipFile(path) as zfp:
            # Locate the dist-info directory.
            # Taken from pip's 'wheel_dist_info_dir utility function.
            #
            # TODO: We should probably eventually require that the dist-info directory
            #       is using normalized values instead of locating them like this.
            subdirs = {p.split("/", 1)[0] for p in zfp.namelist()}
            info_dirs = [s for s in subdirs if s.endswith(".dist-info")]

            if not info_dirs:
                raise InvalidArtifact(
                    f"Wheel {filename!r} does not contain a .dist-info directory",
                )

            if len(info_dirs) > 1:
                raise InvalidArtifact(
                    f"Wheel {filename!r} contains multiple .dist-info directories",
                )

            info_dir = info_dirs[0]

            # Validate that the name and version of the .dist-info directory
            # matches the name and version from the filename.
            #
            # NOTE: While normalization of filenames is currentlya bit of a mess,
            #       pretty much everything assumes that, at a minimum, the version
            #       isn't going to contain a - value, so we can rslit on that.
            dname, dversion = os.path.splitext(info_dir)[0].rsplit("-", 1)
            dname = canonicalize_name(dname)
            dversion = canonicalize_version(dversion)
            if name != dname or version != dversion:
                raise InvalidArtifact(
                    f"Wheel {filename!r} contains a .dist-info directory, "
                    "but it is for a different project or version.",
                )

            metadata_filename = f"{info_dir}/METADATA"

            try:
                metadata_contents = zfp.read(metadata_filename)
            except KeyError:
                raise InvalidArtifact(
                    f"Wheel {filename!r} does not contain a METADATA file",
                )

            return metadata_contents

    return None
