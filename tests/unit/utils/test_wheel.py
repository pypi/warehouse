# SPDX-License-Identifier: Apache-2.0

import zipfile

from pathlib import Path

import pytest

from warehouse.utils import wheel
from warehouse.utils.wheel import InvalidWheelEntryPointsError


@pytest.mark.parametrize(
    ("filename", "expected_tags"),
    [
        ("cryptography-42.0.5.tar.gz", ["Source"]),
        ("Pillow-2.5.0-py3.4-win-amd64.egg", ["Egg"]),
        ("Pillow-2.5.0-py3.4-win32.egg", ["Egg"]),
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
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_intel.whl",
            ["CPython 3.7+", "macOS 10.5+ Intel (x86-64, i386)"],
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_fat.whl",
            ["CPython 3.7+", "macOS 10.5+ fat (i386, PPC)"],
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_fat3.whl",
            ["CPython 3.7+", "macOS 10.5+ fat3 (x86-64, i386, PPC)"],
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_fat64.whl",
            ["CPython 3.7+", "macOS 10.5+ fat64 (x86-64, PPC64)"],
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_universal.whl",
            ["CPython 3.7+", "macOS 10.5+ universal (x86-64, i386, PPC64, PPC)"],
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_12_universal2.whl",
            ["CPython 3.7+", "macOS 10.12+ universal2 (ARM64, x86-64)"],
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_armeabi_v7a.whl",
            ["Android API level 27+ ARM EABI v7a", "CPython 3.13"],
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_arm64_v8a.whl",
            ["Android API level 27+ ARM64 v8a", "CPython 3.13"],
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_x86.whl",
            ["Android API level 27+ x86", "CPython 3.13"],
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_x86_64.whl",
            ["Android API level 27+ x86-64", "CPython 3.13"],
        ),
        (
            "cryptography-42.0.5-cp313-abi3-android_16_armeabi_v7a.whl",
            ["Android API level 16+ ARM EABI v7a", "CPython 3.13+"],
        ),
        (
            "cryptography-42.0.5-cp313-cp313-iOS_15_6_arm64_iphoneos.whl",
            ["CPython 3.13", "iOS 15.6+ ARM64 Device"],
        ),
        (
            "cryptography-42.0.5-cp313-cp313-iOS_15_6_arm64_iphonesimulator.whl",
            ["CPython 3.13", "iOS 15.6+ ARM64 Simulator"],
        ),
        (
            "cryptography-42.0.5-cp313-cp313-iOS_15_6_x86_64_iphonesimulator.whl",
            ["CPython 3.13", "iOS 15.6+ x86-64 Simulator"],
        ),
        (
            "cryptography-42.0.5-cp313-abi3-iOS_13_0_arm64_iphoneos.whl",
            ["CPython 3.13+", "iOS 13.0+ ARM64 Device"],
        ),
        (
            "cryptography-42.0.5-cp313-abi3-iOS_13_0_arm64_iphonesimulator.whl",
            ["CPython 3.13+", "iOS 13.0+ ARM64 Simulator"],
        ),
        (
            "cryptography-42.0.5-cp313-abi3-pyemscripten_2026_0_wasm32.whl",
            ["CPython 3.13+", "PyEmscripten 2026.0 wasm32"],
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
            "numpy-1.26.4-lolinterpreter-lolabi-musllinux_1_1_x86_64.whl",
            ["lolinterpreter", "musllinux: musl 1.1+ x86-64"],
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
        (
            "plato_learn-0.4.7-py36.py37.py38.py39-none-any.whl",
            [
                "Python 3.6",
                "Python 3.7",
                "Python 3.8",
                "Python 3.9",
            ],
        ),
        ("juriscraper-1.1.11-py27-none-any.whl", ["Python 2.7"]),
        ("OZI-0.0.291-py312-none-any.whl", ["Python 3.12"]),
        ("foo-0.0.0-ip27-none-any.whl", ["IronPython 2.7"]),
        ("foo-0.0.0-jy38-none-any.whl", ["Jython 3.8"]),
        ("foo-0.0.0-garbage-none-any.whl", ["garbage"]),
        ("foo-0.0.0-69-none-any.whl", []),
    ],
)
def test_wheel_to_pretty_tags(filename, expected_tags):
    assert wheel.filename_to_pretty_tags(filename) == expected_tags


def _synthesize_entrypoints_wheel(ini_contents: bytes, tmp_path: Path) -> Path:
    """
    Synthesize a temporary (partial) wheel file containing the given
    entry point contents.
    """

    wheel_path = tmp_path / "test-0.0.1-py3-none-any.whl"

    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            "test-0.0.1.dist-info/entry_points.txt",
            ini_contents,
        )

    return wheel_path


@pytest.mark.parametrize("section_name", ["console_scripts", "gui_scripts"])
@pytest.mark.parametrize(
    ("entrypoint_name", "valid"),
    [
        # Valid names.
        ("foo", True),
        ("foo.bar", True),
        ("foo_bar", True),
        ("foo-bar", True),
        ("foo123", True),
        ("123foo", True),
        ("_foo", True),
        ("foo_", True),
        ("foo.", True),
        (".foo", True),
        ("foo..bar", True),
        ("_", True),
        ("-_-", True),
        # Invalid names.
        ("' '", False),
        ("''", False),
        ("foo bar", False),
        ("foo\tbar", False),
        ("foo\rbar", False),
        ("foo/bar", False),
        ("foo\\bar", False),
        ("foo:bar", False),
        ("'foo:bar'", False),
        ("C:\\foo", False),
        ("'C:\\foo'", False),
        ("..\\..\\foo", False),
        ("/foo", False),
        ("../../../../foo", False),
    ],
)
def test_validate_entrypoints_names(section_name, entrypoint_name, valid, tmp_path):
    int_contents = f"[{section_name}]\n{entrypoint_name}=foo:main\n"
    wheel_path = _synthesize_entrypoints_wheel(int_contents.encode(), tmp_path)

    if valid:
        # Should not raise an exception.
        wheel.validate_entrypoints(str(wheel_path))
    else:
        with pytest.raises(
            InvalidWheelEntryPointsError,
            match="Invalid entry point name",
        ):
            wheel.validate_entrypoints(str(wheel_path))


@pytest.mark.parametrize(
    ("contents", "error"),
    [
        # Not valid UTF-8.
        (b"\xff\xfe\xfd", "not decodable as UTF-8"),
        # Uses : instead of = as the delimiter.
        (b"[console_scripts]\nfoo:main\n", "is not a valid INI file"),
    ],
)
def test_validate_entrypoints_invalid_syntax(contents, error, tmp_path):
    wheel_path = _synthesize_entrypoints_wheel(contents, tmp_path)
    with pytest.raises(
        InvalidWheelEntryPointsError,
        match=error,
    ):
        wheel.validate_entrypoints(str(wheel_path))


def test_validate_entrypoints_no_console_scripts(tmp_path):
    int_contents = b"[not_console_scripts]\n/foo/ = bar:main\n"
    wheel_path = _synthesize_entrypoints_wheel(int_contents, tmp_path)

    # Should not raise an exception since there are no console scripts to validate.
    assert wheel.validate_entrypoints(str(wheel_path)) is True


def test_validate_entrypoints_ok(tmp_path):
    # Example taken directly from the Entry Points specification.
    ini_contents = """
[console_scripts]
foo = foomod:main
# One which depends on extras:
foobar = foomod:main_bar [bar,baz]

# pytest plugins refer to a module, so there is no ':obj'
[pytest11]
nbval = nbval.plugin
"""

    wheel_path = _synthesize_entrypoints_wheel(ini_contents.encode(), tmp_path)
    assert wheel.validate_entrypoints(str(wheel_path)) is True
