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

from typing import Iterator, List, Tuple


class HashBins:
    """
    Hash Bins management

    This code is inspired on python-tuf repo examples for hash bins
    """

    def __init__(self, number_of_bins: int) -> None:
        """
        Hash Bins

        Args:
            number_of_bins: number of bins
        """
        self.number_of_bins = number_of_bins
        # The prefix length is the number of digits in the hexadecimal representation
        # (see 'x' in Python Format Specification) of the number of bins minus one
        # (counting starts at zero), i.e. ...
        self.prefix_len = len(f"{(self.number_of_bins - 1):x}")  # ... 2.
        # Compared to decimal, hexadecimal numbers can express higher numbers
        # with fewer digits and thus further decrease metadata sizes. With the
        # above prefix length of 2 we can represent at most 256 prefixes, i.e.
        # 00, 01, ..., ff.
        self.number_of_prefixes = 16**self.prefix_len
        # If the number of bins is a power of two, hash prefixes are evenly
        # distributed over all bins, which allows to calculate the uniform size
        # of 8, where each bin is responsible for a range of 8 prefixes, i.e.
        # 00-07, 08-0f, ..., f8-ff.
        self.bin_size = self.number_of_prefixes // self.number_of_bins

    def _bin_name(self, low: int, high: int) -> str:
        """
        Generates a bin name according to the hash prefixes the bin serves.

        The name is either a single hash prefix for bin size 1, or a range of hash
        prefixes otherwise. The prefix length is needed to zero-left-pad the
        hex representation of the hash prefix for uniform bin name lengths.
        """
        if low == high:
            return f"{low:0{self.prefix_len}x}"

        return f"{low:0{self.prefix_len}x}-{high:0{self.prefix_len}x}"

    def generate(self) -> Iterator[Tuple[str, List[str]]]:
        """Returns generator for bin names and hash prefixes per bin."""
        # Iterate over the total number of hash prefixes in 'bin size'-steps to
        # generate bin names and a list of hash prefixes served by each bin.
        for low in range(0, self.number_of_prefixes, self.bin_size):
            high = low + self.bin_size - 1
            bin_name = self._bin_name(low, high)
            hash_prefixes = []
            for prefix in range(low, low + self.bin_size):
                hash_prefixes.append(f"{prefix:0{self.prefix_len}x}")

            yield bin_name, hash_prefixes

    def get_delegate(self, file_path: str) -> str:
        """
        Gets the delegated role name bin based on the target file path.

        Args:
            file_path

        Returns:
            bin name low-high
        """
        hasher = hashlib.sha256()
        hasher.update(file_path.encode("utf-8"))
        target_name_hash = hasher.hexdigest()
        prefix = int(target_name_hash[: self.prefix_len], 16)
        low = prefix - (prefix % self.bin_size)
        high = low + self.bin_size - 1
        return self._bin_name(low, high)
