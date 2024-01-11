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

import hashlib
import io


class HashedFileWrapper:
    def __init__(self, fp: io.RawIOBase, hashers: dict[str, hashlib._Hash]):
        self._fp = fp
        self._hashers = hashers

    def __getattr__(self, name):
        return getattr(self._fp, name)

    def read(self, size=-1, /) -> bytes:
        chunk = self._fp.read(size)

        for hasher in self._hashers.values():
            hasher.update(chunk)

        return chunk

    def digests(self) -> dict[str, str]:
        return {
            name: hasher.hexdigest().lower() for name, hasher in self._hashers.items()
        }


class FileLimitError(Exception):
    pass


class LimitedFileWrapper:
    def __init__(self, fp: io.RawIOBase, limit: int):
        self._fp = fp
        self._limit = limit
        self._amount_read = 0

    def __getattr__(self, name):
        return getattr(self._fp, name)

    def read(self, size=-1, /) -> bytes:
        chunk = self._fp.read(size)
        self._amount_read += len(chunk)

        if self._amount_read > self._limit:
            raise FileLimitError

        return chunk

    @property
    def amount_read(self) -> int:
        return self._amount_read
