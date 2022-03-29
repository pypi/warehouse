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

from warehouse.tuf.hash_bins import HashBins


class TestHashBins:
    def test_basic_init(self):
        test_hash_bins = HashBins(32)
        assert test_hash_bins.number_of_bins == 32
        assert test_hash_bins.prefix_len == 2
        assert test_hash_bins.number_of_prefixes == 256
        assert test_hash_bins.bin_size == 8

        test_hash_bins = HashBins(16)
        assert test_hash_bins.number_of_bins == 16
        assert test_hash_bins.prefix_len == 1
        assert test_hash_bins.number_of_prefixes == 16
        assert test_hash_bins.bin_size == 1

    def test__bin_name(self):
        test_hash_bins = HashBins(32)
        assert test_hash_bins._bin_name(1, 7) == "01-07"
        assert test_hash_bins._bin_name(32, 39) == "20-27"

    def test_generate(self):
        test_hash_bins = HashBins(16)
        hash_bin_list = [
            ("0", ["0"]),
            ("1", ["1"]),
            ("2", ["2"]),
            ("3", ["3"]),
            ("4", ["4"]),
            ("5", ["5"]),
            ("6", ["6"]),
            ("7", ["7"]),
            ("8", ["8"]),
            ("9", ["9"]),
            ("a", ["a"]),
            ("b", ["b"]),
            ("c", ["c"]),
            ("d", ["d"]),
            ("e", ["e"]),
            ("f", ["f"]),
        ]
        for i in test_hash_bins.generate():
            assert i in hash_bin_list

    def test_get_delegate(self):
        test_hash_bins = HashBins(128)
        assert test_hash_bins.get_delegate("filepath0") == "24-25"
        assert test_hash_bins.get_delegate("filepath1") == "d8-d9"
