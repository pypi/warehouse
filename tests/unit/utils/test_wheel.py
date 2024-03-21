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

import pytest

from warehouse.utils import wheel


@pytest.mark.parametrize(
    ("filename", "expected_tags"),
    [
        ("cryptography-42.0.5.tar.gz", ["Source"]),
        (
            "cryptography-42.0.5-pp310-pypy310_pp73-win_amd64.whl",
            ["PyPy", "Windows x86-64"],
        ),
        (
            "cryptography-42.0.5-pp310-pypy310_pp73-manylinux_2_28_x86_64.whl",
            ["PyPy", "manylinux: glibc 2.28+ x86-64"],
        ),
        (
            "cryptography-42.0.5-cp37-abi3-musllinux_1_2_x86_64.whl",
            ["CPython 3.7+", "musllinux: musl 1.2+ x86-64"],
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_12_universal2.whl",
            ["CPython 3.7+", "macOS 10.12+ universal2 (ARM64, x86-64)"],
        ),
        (
            "pgf-1.0-pp27-pypy_73-manylinux2010_x86_64.whl",
            ["PyPy", "manylinux: glibc 2.12+ x86-64"],
        ),
        ("pdfcomparator-0_2_0-py2-none-any.whl", []),
        (
            "mclbn256-0.6.0-py3-abi3-macosx_12_0_arm64.whl",
            ["Python 3", "macOS 12.0+ ARM64"],
        ),
        (
            "pep272_encryption-0.4-py2.pp35.pp36.pp37.pp38.pp39-none-any.whl",
            ["PyPy", "Python 2"],
        ),
        (
            "ruff-0.3.2-py3-none-musllinux_1_2_armv7l.whl",
            ["Python 3", "musllinux: musl 1.2+ ARMv7l"],
        ),
        (
            "numpy-1.26.4-cp312-cp312-musllinux_1_1_x86_64.whl",
            ["CPython 3.12", "musllinux: musl 1.1+ x86-64"],
        ),
        (
            "numpy-1.26.4-lol-lol-musllinux_1_1_x86_64.whl",
            ["musllinux: musl 1.1+ x86-64"],
        ),
        (
            (
                "pydantic_core-2.16.2-pp39-pypy39_pp73-manylinux_2_17_aarch64."
                "manylinux2014_aarch64.whl"
            ),
            ["PyPy", "manylinux: glibc 2.17+ ARM64"],
        ),
        ("numpy-1.13.1-cp36-none-win_amd64.whl", ["CPython 3.6", "Windows x86-64"]),
        ("cryptography-38.0.2-cp36-abi3-win32.whl", ["CPython 3.6+", "Windows x86"]),
    ],
)
def test_wheel_to_pretty_tags(filename, expected_tags):
    assert wheel.filename_to_pretty_tags(filename) == expected_tags
