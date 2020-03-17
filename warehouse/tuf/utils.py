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

import tuf.formats


def make_fileinfo(file, custom=None):
    """
    Given a warehouse.packaging.models.File, create a TUF-compliant
    "fileinfo" dictionary suitable for addition to a delegated bin.

    The optional "custom" kwarg can be used to supply additional custom
    metadata (e.g., metadata for indicating backsigning).
    """
    hashes = {"blake2b": file.blake2_256_digest}
    fileinfo = tuf.formats.make_fileinfo(file.size, hashes, custom=custom)

    return fileinfo
