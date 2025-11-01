# SPDX-License-Identifier: Apache-2.0

import re

import packaging.tags
import packaging.utils

# Map known Python tags, ABI tags, Platform tags to labels.
_PLATFORM_MAP = {
    "win": [(re.compile(r"^win_(.*?)$"), lambda m: f"Windows {_norm_arch(m.group(1))}")],
    "win32": [(re.compile(r"^win32$"), lambda m: "Windows x86")],
    "manylinux": [(
        re.compile(r"^manylinux_(\d+)_(\d+)_(.*?)$"),
        lambda m: f"linux glibc {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))}"

    )],
    "manylinux2014": [(
        re.compile(r"^manylinux2014_(.*?)$"),
        lambda m: f"linux glibc 2.17+ {_norm_arch(m.group(1))}",
    )],
    "manylinux2010": [(
        re.compile(r"^manylinux2010_(.*?)$"),
        lambda m: f"linux glibc 2.12+ {_norm_arch(m.group(1))}",
    )],
    "manylinux1": [(
        re.compile(r"^manylinux1_(.*?)$"),
        lambda m: f"linux glibc 2.5+ {_norm_arch(m.group(1))}",
    )],
    "musllinux": [(
        re.compile(r"^musllinux_(\d+)_(\d+)_(.*?)$"),
        lambda m: f"linux musl {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))}"
    )],
    "macosx": [(
        re.compile(r"^macosx_(\d+)_(\d+)_(.*?)$"),
        lambda m: f"macOS {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))}",
    )],
    "ios": [(
        re.compile(r"^ios_(\d+)_(\d+)_(.*?)_iphoneos$"),
        lambda m: f"iOS {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))} Device",  # noqa: E501
    ),
        (
            re.compile(r"^ios_(\d+)_(\d+)_(.*?)_iphonesimulator$"),
            lambda m: f"iOS {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))} Simulator",  # noqa: E501
        )],
    "android":
        [(
            re.compile(r"^android_(\d+)_(.*?)$"),
            lambda m: f"Android API level {m.group(1)}+ {_norm_arch(m.group(2))}",
        )],
}
_ARCH_MAP = {
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
    "i686": "x86-32",
    "ppc64": "PowerPC 64-be",
    "ppc64le": "PowerPC 64-le",
    "s390x": "IBM System/390x",
    "riscv64": "RISC-V 64",
}
_CPYTHON_SUFFIX_MAP = {
    "d": "debug",
    "m": "pymalloc",
    "t": "free-threading",
    "u": "wide-unicode",
}


def _format_version(s: str) -> str:
    return f"{s[0]}.{s[1:]}"


def _norm_arch(a: str) -> str:
    return _ARCH_MAP.get(a, a)


def _norm_str(s: str) -> str:
    return (s or "").replace('_', ' ').strip()


def _implementation_to_label(raw: str) -> str:
    if raw.startswith("pypy"):
        version = _norm_str(raw.removeprefix("pypy"))
        return f"PyPy {version}"
    elif raw.startswith("py"):
        major, minor = raw[2:3], raw[3:]
        return f"Python {major}{'.' if minor else ''}{minor}"
    elif raw.startswith("cp"):
        version, suffixes = _format_cpython(raw.removeprefix("cp"))
        return f"CPython {version} {suffixes}".strip()
    elif raw.startswith("pp"):
        version = _norm_str(raw.removeprefix("pp"))
        return f"PyPy {version}"
    elif raw.startswith("ip"):
        major, minor = raw[2:3], raw[3:]
        return f"IronPython {major}{'.' if minor else ''}{minor}"
    elif raw.startswith("jy"):
        major, minor = raw[2:3], raw[3:]
        version = f"{major}{'.' if minor else ''}{minor}"
        return f"Jython {version}"
    else:
        # Unknown format. Normalise and return it.
        return _norm_str(raw)


def _format_cpython(s: str) -> tuple[str, str]:
    suffixes = []
    raw = (s or "").strip()
    while raw[-1].isalpha():
        last_char = raw[-1]
        name = _CPYTHON_SUFFIX_MAP.get(last_char)
        if not name:
            # Unknown CPython abi suffix. Just include it.
            name = last_char
        suffixes.append(name)
        raw = raw[0:-1]
    version = _format_version(raw)
    return version, ' '.join(sorted(suffixes))


def _interpreter_to_label(tag: packaging.tags.Tag) -> str:
    return _implementation_to_label(tag.interpreter)


def _abi_to_label(tag: packaging.tags.Tag) -> str:
    if tag.abi == "none":
        return "(none)"
    elif tag.abi == "abi3":
        # NOTE: CPython abi3 should have a CPython interpreter.
        # if not tag.interpreter.startswith("cp"):
        # A non- CPython interpreter with CPython abi3.
        # Should this be possible?
        # pass
        return "CPython abi3"
    elif tag.abi.startswith("cp"):
        return _implementation_to_label(tag.abi)
    elif tag.abi.startswith("pypy"):
        return _implementation_to_label(tag.abi)
    elif tag.abi.startswith("pp"):
        return _implementation_to_label(tag.abi)
    elif tag.abi.startswith("ip"):
        return _implementation_to_label(tag.abi)
    elif tag.abi.startswith("jy"):
        return _implementation_to_label(tag.abi)
    else:
        # Unknown abi. Just return it.
        return _norm_str(tag.abi)


def _platform_to_label(tag: packaging.tags.Tag) -> str:
    if tag.platform == 'any':
        return "(any)"

    value = tag.platform
    key = value.split('_', maxsplit=1)[0] if '_' in value else value

    patterns = _PLATFORM_MAP.get(key, [])
    for (prefix_re, tmpl) in patterns:
        if match := prefix_re.match(value):
            return tmpl(match)

    # Unknown platform. Just return it
    return _norm_str(value)


def _add_group_label(container: dict, group: str, value: str, label: str) -> None:
    if value not in container[group]:
        container[group][value] = label
    elif container[group][value] != label:
        # A value that is already present, with a different label.
        # This looks odd. Is this possible?
        # Use the most recently seen label.
        container[group][value] = label


def filename_to_tags(filename: str) -> set[packaging.tags.Tag]:
    """Parse a wheel file name to extract the tags."""
    try:
        _, _, _, tags = packaging.utils.parse_wheel_filename(filename)
        return set(tags)
    except packaging.utils.InvalidWheelFilename:
        return set()


def filename_to_pretty_tags(filename: str) -> list[str]:
    grouped_labels = filename_to_grouped_labels(filename)
    pretty_tags = set()
    for kind, kind_items in grouped_labels.items():
        for value, label in kind_items.items():
            pretty_tags.add(label)
    return sorted(pretty_tags)


def filename_to_grouped_labels(filename: str) -> dict[str, dict]:
    grouped_labels = {
        "interpreter": {},
        "abi": {},
        "platform": {},
        "other": {},
    }

    if filename.endswith(".egg"):
        grouped_labels['other']['egg'] = "Egg"
        return grouped_labels
    elif not filename.endswith(".whl"):
        grouped_labels['other']['source'] = "Source"
        return grouped_labels

    tags = filename_to_tags(filename)
    for tag in tags:
        _add_group_label(grouped_labels, "interpreter", tag.interpreter, _interpreter_to_label(tag))
        _add_group_label(grouped_labels, "abi", tag.abi, _abi_to_label(tag))
        _add_group_label(grouped_labels, "platform", tag.platform, _platform_to_label(tag))
    return grouped_labels


def filenames_to_grouped_labels(filenames: list[str]) -> dict[str, dict]:
    grouped_labels = {
        "interpreter": {},
        "abi": {},
        "platform": {},
        "other": {},
    }
    for filename in filenames:
        grouped = filename_to_grouped_labels(filename)
        for kind, kind_items in grouped.items():
            if kind not in grouped_labels:
                grouped_labels[kind] = {}
            for value, label in kind_items.items():
                if value not in grouped_labels[kind]:
                    grouped_labels[kind][value] = label
    return grouped_labels
