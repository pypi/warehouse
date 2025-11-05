# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.utils import wheel


def _build(**kwargs):
    grouped_labels = {
        "interpreter": {},
        "abi": {},
        "platform": {},
        "other": {},
    }
    for key, value in kwargs.items():
        if key.startswith("interp_"):
            grouped_labels["interpreter"][key.removeprefix("interp_")] = value
        elif key.startswith("abi_"):
            grouped_labels["abi"][key.removeprefix("abi_")] = value
        elif key.startswith("plat_"):
            grouped_labels["platform"][key.removeprefix("plat_")] = value
        elif key.startswith("other_"):
            grouped_labels["other"][key.removeprefix("other_")] = value
        else:
            raise ValueError(f"Unknown item {key}={value}")
    return grouped_labels


@pytest.mark.parametrize(
    ("filename", "expected_tags"),
    [
        ("cryptography-42.0.5.tar.gz", _build(other_source="Source")),
        ("Pillow-2.5.0-py3.4-win-amd64.egg", _build(other_egg="Egg")),
        ("Pillow-2.5.0-py3.4-win32.egg", _build(other_egg="Egg")),
        (
            "cryptography-42.0.5-pp310-pypy310_pp73-win_amd64.whl",
            _build(
                interp_pp310="PyPy 310",
                abi_pypy310_pp73="PyPy 310 pp73",
                plat_win_amd64="Windows x86-64",
            ),
        ),
        (
            "cryptography-42.0.5-pp310-pypy310_pp73-manylinux_2_28_x86_64.whl",
            _build(
                interp_pp310="PyPy 310",
                abi_pypy310_pp73="PyPy 310 pp73",
                plat_manylinux_2_28_x86_64="linux glibc 2.28+ x86-64",
            ),
        ),
        (
            "cryptography-42.0.5-cp37-abi3-musllinux_1_2_x86_64.whl",
            _build(
                interp_cp37="CPython 3.7",
                abi_abi3="CPython abi3",
                plat_musllinux_1_2_x86_64="linux musl 1.2+ x86-64",
            ),
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_intel.whl",
            _build(
                interp_cp37="CPython 3.7",
                abi_abi3="CPython abi3",
                plat_macosx_10_5_intel="macOS 10.5+ Intel (x86-64, i386)",
            ),
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_fat.whl",
            _build(
                interp_cp37="CPython 3.7",
                abi_abi3="CPython abi3",
                plat_macosx_10_5_fat="macOS 10.5+ fat (i386, PPC)",
            ),
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_fat3.whl",
            _build(
                interp_cp37="CPython 3.7",
                abi_abi3="CPython abi3",
                plat_macosx_10_5_fat3="macOS 10.5+ fat3 (x86-64, i386, PPC)",
            ),
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_fat64.whl",
            _build(
                interp_cp37="CPython 3.7",
                abi_abi3="CPython abi3",
                plat_macosx_10_5_fat64="macOS 10.5+ fat64 (x86-64, PPC64)",
            ),
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_5_universal.whl",
            _build(
                interp_cp37="CPython 3.7",
                abi_abi3="CPython abi3",
                plat_macosx_10_5_universal="macOS 10.5+ "
                "universal (x86-64, i386, PPC64, PPC)",
            ),
        ),
        (
            "cryptography-42.0.5-cp37-abi3-macosx_10_12_universal2.whl",
            _build(
                interp_cp37="CPython 3.7",
                abi_abi3="CPython abi3",
                plat_macosx_10_12_universal2="macOS 10.12+ universal2 (ARM64, x86-64)",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_armeabi_v7a.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_cp313="CPython 3.13",
                plat_android_27_armeabi_v7a="Android API level 27+ ARM EABI v7a",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_arm64_v8a.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_cp313="CPython 3.13",
                plat_android_27_arm64_v8a="Android API level 27+ ARM64 v8a",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_x86.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_cp313="CPython 3.13",
                plat_android_27_x86="Android API level 27+ x86",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-cp313-android_27_x86_64.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_cp313="CPython 3.13",
                plat_android_27_x86_64="Android API level 27+ x86-64",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-abi3-android_16_armeabi_v7a.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_abi3="CPython abi3",
                plat_android_16_armeabi_v7a="Android API level 16+ ARM EABI v7a",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-cp313-iOS_15_6_arm64_iphoneos.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_cp313="CPython 3.13",
                plat_ios_15_6_arm64_iphoneos="iOS 15.6+ ARM64 Device",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-cp313-iOS_15_6_arm64_iphonesimulator.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_cp313="CPython 3.13",
                plat_ios_15_6_arm64_iphonesimulator="iOS 15.6+ ARM64 Simulator",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-cp313-iOS_15_6_x86_64_iphonesimulator.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_cp313="CPython 3.13",
                plat_ios_15_6_x86_64_iphonesimulator="iOS 15.6+ x86-64 Simulator",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-abi3-iOS_13_0_arm64_iphoneos.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_abi3="CPython abi3",
                plat_ios_13_0_arm64_iphoneos="iOS 13.0+ ARM64 Device",
            ),
        ),
        (
            "cryptography-42.0.5-cp313-abi3-iOS_13_0_arm64_iphonesimulator.whl",
            _build(
                interp_cp313="CPython 3.13",
                abi_abi3="CPython abi3",
                plat_ios_13_0_arm64_iphonesimulator="iOS 13.0+ ARM64 Simulator",
            ),
        ),
        (
            "pgf-1.0-pp27-pypy_73-manylinux2010_x86_64.whl",
            _build(
                interp_pp27="PyPy 27",
                abi_pypy_73="PyPy 73",
                plat_manylinux2010_x86_64="linux glibc 2.12+ x86-64",
            ),
        ),
        # Cannot parse 'pdfcomparator-0_2_0-py2-none-any.whl' - invalid version?
        (
            "pdfcomparator-0_2_0-py2-none-any.whl",
            # _build(interp_py2="Python 2", abi_none="(none)", plat_any="(any)")),
            _build(),
        ),
        (
            "mclbn256-0.6.0-py3-abi3-macosx_12_0_arm64.whl",
            _build(
                interp_py3="Python 3",
                abi_abi3="CPython abi3",
                plat_macosx_12_0_arm64="macOS 12.0+ ARM64",
            ),
        ),
        (
            "pep272_encryption-0.4-py2.pp35.pp36.pp37.pp38.pp39-none-any.whl",
            _build(
                interp_py2="Python 2",
                interp_pp35="PyPy 35",
                interp_pp36="PyPy 36",
                interp_pp37="PyPy 37",
                interp_pp38="PyPy 38",
                interp_pp39="PyPy 39",
                abi_none="(none)",
                plat_any="(any)",
            ),
        ),
        (
            "ruff-0.3.2-py3-none-musllinux_1_2_armv7l.whl",
            _build(
                interp_py3="Python 3",
                abi_none="(none)",
                plat_musllinux_1_2_armv7l="linux musl 1.2+ ARMv7l",
            ),
        ),
        (
            "numpy-1.26.4-cp312-cp312-musllinux_1_1_x86_64.whl",
            _build(
                interp_cp312="CPython 3.12",
                abi_cp312="CPython 3.12",
                plat_musllinux_1_1_x86_64="linux musl 1.1+ x86-64",
            ),
        ),
        (
            "numpy-1.26.4-lol_interpreter-lol_abi-lol_platform.whl",
            _build(
                interp_lol_interpreter="lol interpreter",
                abi_lol_abi="lol abi",
                plat_lol_platform="lol platform",
            ),
        ),
        (
            "pydantic_core-2.16.2-pp39-pypy39_pp73-"
            "manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
            _build(
                interp_pp39="PyPy 39",
                abi_pypy39_pp73="PyPy 39 pp73",
                plat_manylinux_2_17_aarch64="linux glibc 2.17+ ARM64",
                plat_manylinux2014_aarch64="linux glibc 2.17+ ARM64",
            ),
        ),
        (
            "numpy-1.13.1-cp36-none-win_amd64.whl",
            _build(
                interp_cp36="CPython 3.6",
                abi_none="(none)",
                plat_win_amd64="Windows x86-64",
            ),
        ),
        (
            "cryptography-38.0.2-cp36-abi3-win32.whl",
            _build(
                interp_cp36="CPython 3.6",
                abi_abi3="CPython abi3",
                plat_win32="Windows x86",
            ),
        ),
        (
            "plato_learn-0.4.7-py36.py37.py38.py39-none-any.whl",
            _build(
                interp_py36="Python 3.6",
                interp_py37="Python 3.7",
                interp_py38="Python 3.8",
                interp_py39="Python 3.9",
                abi_none="(none)",
                plat_any="(any)",
            ),
        ),
        (
            "juriscraper-1.1.11-py27-none-any.whl",
            _build(interp_py27="Python 2.7", abi_none="(none)", plat_any="(any)"),
        ),
        (
            "OZI-0.0.291-py312-none-any.whl",
            _build(interp_py312="Python 3.12", abi_none="(none)", plat_any="(any)"),
        ),
        (
            "foo-0.0.0-ip27-none-any.whl",
            _build(interp_ip27="IronPython 2.7", abi_none="(none)", plat_any="(any)"),
        ),
        (
            "foo-0.0.0-jy38-none-any.whl",
            _build(interp_jy38="Jython 3.8", abi_none="(none)", plat_any="(any)"),
        ),
        (
            "foo-0.0.0-garbage-none-any.whl",
            _build(interp_garbage="garbage", abi_none="(none)", plat_any="(any)"),
        ),
        (
            "foo-0.0.0-69-none-any.whl",
            _build(interp_69="69", abi_none="(none)", plat_any="(any)"),
        ),
        (
            "aiohttp-3.13.2-cp314-cp314udmtz-"
            "manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl",
            _build(
                interp_cp314="CPython 3.14",
                abi_cp314udmtz="CPython 3.14 "
                "debug free-threading pymalloc wide-unicode z",
                plat_manylinux_2_31_riscv64="linux glibc 2.31+ RISC-V 64",
                plat_manylinux_2_39_riscv64="linux glibc 2.39+ RISC-V 64",
            ),
        ),
        (
            "aiohttp-3.13.2-cp314-cp314t-"
            "manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl",
            _build(
                interp_cp314="CPython 3.14",
                abi_cp314t="CPython 3.14 free-threading",
                plat_manylinux2014_s390x="linux glibc 2.17+ IBM System/390x",
                plat_manylinux_2_17_s390x="linux glibc 2.17+ IBM System/390x",
                plat_manylinux_2_28_s390x="linux glibc 2.28+ IBM System/390x",
            ),
        ),
        (
            "aiohttp-3.13.2-cp39-cp39-"
            "manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl",
            _build(
                interp_cp39="CPython 3.9",
                abi_cp39="CPython 3.9",
                plat_manylinux2014_ppc64le="linux glibc 2.17+ PowerPC 64-le",
                plat_manylinux_2_17_ppc64le="linux glibc 2.17+ PowerPC 64-le",
                plat_manylinux_2_28_ppc64le="linux glibc 2.28+ PowerPC 64-le",
            ),
        ),
        (
            "numpy-2.3.4-pp311-pypy311_pp73-"
            "manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl",
            _build(
                interp_pp311="PyPy 311",
                abi_pypy311_pp73="PyPy 311 pp73",
                plat_manylinux_2_27_aarch64="linux glibc 2.27+ ARM64",
                plat_manylinux_2_28_aarch64="linux glibc 2.28+ ARM64",
            ),
        ),
        (
            "numpy-2.3.4-pp311-pp73_pypy311-"
            "manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl",
            _build(
                interp_pp311="PyPy 311",
                abi_pp73_pypy311="PyPy 73 pypy311",
                plat_manylinux_2_27_aarch64="linux glibc 2.27+ ARM64",
                plat_manylinux_2_28_aarch64="linux glibc 2.28+ ARM64",
            ),
        ),
        (
            "numpy-2.3.4-pp311-ip27-"
            "manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl",
            _build(
                interp_pp311="PyPy 311",
                abi_ip27="IronPython 2.7",
                plat_manylinux_2_27_aarch64="linux glibc 2.27+ ARM64",
                plat_manylinux_2_28_aarch64="linux glibc 2.28+ ARM64",
            ),
        ),
        (
            "numpy-2.3.4-pp311-jy38-"
            "manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl",
            _build(
                interp_pp311="PyPy 311",
                abi_jy38="Jython 3.8",
                plat_manylinux_2_27_aarch64="linux glibc 2.27+ ARM64",
                plat_manylinux_2_28_aarch64="linux glibc 2.28+ ARM64",
            ),
        ),
    ],
)
def test_wheel_to_groups_labels(filename, expected_tags):
    assert wheel.filename_to_grouped_labels(filename) == expected_tags
