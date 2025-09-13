# SPDX-License-Identifier: Apache-2.0

import re

import packaging.tags
import packaging.utils

# import sentry_sdk

_PLATFORMS = [
    (re.compile(r"^win_(.*?)$"), lambda m: f"Windows {_normalize_arch(m.group(1))}"),
    (re.compile(r"^win32$"), lambda m: "Windows x86"),
    (
        re.compile(r"^manylinux2010_(.*?)$"),
        lambda m: f"manylinux: glibc 2.12+ {_normalize_arch(m.group(1))}",
    ),
    (
        re.compile(r"^manylinux_(\d+)_(\d+)_(.*?)$"),
        lambda m: (
            f"manylinux: glibc "
            f"{m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))}"
        ),
    ),
    (
        re.compile(r"^musllinux_(\d+)_(\d+)_(.*?)$"),
        lambda m: (
            f"musllinux: musl {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))}"
        ),
    ),
    (
        re.compile(r"^macosx_(\d+)_(\d+)_(.*?)$"),
        lambda m: f"macOS {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))}",
    ),
    (
        re.compile(r"^android_(\d+)_(.*?)$"),
        lambda m: f"Android API level {m.group(1)}+ {_normalize_arch(m.group(2))}",
    ),
    (
        re.compile(r"^ios_(\d+)_(\d+)_(.*?)_iphoneos$"),
        lambda m: f"iOS {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))} Device",  # noqa: E501
    ),
    (
        re.compile(r"^ios_(\d+)_(\d+)_(.*?)_iphonesimulator$"),
        lambda m: f"iOS {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))} Simulator",  # noqa: E501
    ),
]

_ARCHS = {
    "amd64": "x86-64",
    "aarch64": "ARM64",
    "armeabi_v7a": "ARM EABI v7a",
    "arm64_v8a": "ARM64 v8a",
    "x86_64": "x86-64",
    "intel": "Intel (x86-64, i386)",
    "fat": "fat (i386, PPC)",
    "fat3": "fat3 (x86-64, i386, PPC)",
    "fat64": "fat64 (x86-64, PPC64)",
    "universal": "universal (x86-64, i386, PPC64, PPC)",
    "universal2": "universal2 (ARM64, x86-64)",
    "arm64": "ARM64",
    "armv7l": "ARMv7l",
}


def _normalize_arch(a: str) -> str:
    return _ARCHS.get(a, a)


def _format_version(s: str) -> str:
    return f"{s[0]}.{s[1:]}"


def filename_to_tags(filename: str) -> set[packaging.tags.Tag]:
    """Parse a wheel file name to extract the tags."""
    try:
        _, _, _, tags = packaging.utils.parse_wheel_filename(filename)
        return set(tags)
    except packaging.utils.InvalidWheelFilename:
        return set()


def filename_to_pretty_tags(filename: str) -> list[str]:
    if filename.endswith(".egg"):
        return ["Egg"]
    elif not filename.endswith(".whl"):
        return ["Source"]

    tags = filename_to_tags(filename)

    pretty_tags = set()
    for tag in tags:
        if tag.platform != "any":
            for prefix_re, tmpl in _PLATFORMS:
                if match := prefix_re.match(tag.platform):
                    pretty_tags.add(tmpl(match))

        if len(tag.interpreter) < 3 or not tag.interpreter[:2].isalpha():
            # This tag doesn't fit our format, give up
            pass
        elif tag.interpreter.startswith("pp"):
            # PyPy tags are a disaster, give up.
            pretty_tags.add("PyPy")
        elif tag.interpreter.startswith("py"):
            major, minor = tag.interpreter[2:3], tag.interpreter[3:]
            pretty_tags.add(f"Python {major}{'.' if minor else ''}{minor}")
        elif tag.interpreter.startswith("ip"):
            major, minor = tag.interpreter[2:3], tag.interpreter[3:]
            pretty_tags.add(f"IronPython {major}{'.' if minor else ''}{minor}")
        elif tag.interpreter.startswith("jy"):
            major, minor = tag.interpreter[2:3], tag.interpreter[3:]
            pretty_tags.add(f"Jython {major}{'.' if minor else ''}{minor}")
        elif tag.abi == "abi3":
            assert tag.interpreter.startswith("cp")
            version = _format_version(tag.interpreter.removeprefix("cp"))
            pretty_tags.add(f"CPython {version}+")
        elif tag.abi.startswith("cp"):
            version = _format_version(tag.abi.removeprefix("cp"))
            pretty_tags.add(f"CPython {version}")
        elif tag.interpreter.startswith("cp"):
            version = _format_version(tag.interpreter.removeprefix("cp"))
            pretty_tags.add(f"CPython {version}")
        else:
            # There's a lot of cruft from over the years. If we can't identify
            # the interpreter tag, just add it directly.
            pretty_tags.add(tag.interpreter)

    return sorted(pretty_tags)


def filenames_to_filters(filenames: list[str]) -> dict[str, list[str]]:
    tags = set()
    for filename in filenames:
        tags.update(filename_to_tags(filename))
    return tags_to_filters(tags)


def filename_to_filters(filename: str) -> dict[str, list[str]]:
    tags = filename_to_tags(filename)
    return tags_to_filters(tags)


def tags_to_filters(tags: set[packaging.tags.Tag]) -> dict[str, list[str]]:
    interpreters = set()
    abis = set()
    platforms = set()
    for tag in tags or []:
        interpreters.add(tag.interpreter)
        abis.add(tag.abi)
        platforms.add(tag.platform)

    return {
        "interpreters": sorted(interpreters),
        "abis": sorted(abis),
        "platforms": sorted(platforms),
    }
