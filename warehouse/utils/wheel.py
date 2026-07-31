# SPDX-License-Identifier: Apache-2.0

import configparser
import csv
import os
import re
import sys
import zipfile

import packaging.tags
import packaging.utils


class MissingWheelRecordError(Exception):
    """Internal exception used by this module"""


class InvalidWheelRecordError(Exception):
    """Internal exception used by this module"""


class InvalidWheelEntryPointsError(Exception):
    """Internal exception used by this module"""


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
            f"manylinux: glibc {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))}"
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
        lambda m: (
            f"iOS {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))} Device"
        ),
    ),
    (
        re.compile(r"^ios_(\d+)_(\d+)_(.*?)_iphonesimulator$"),
        lambda m: (
            f"iOS {m.group(1)}.{m.group(2)}+ {_normalize_arch(m.group(3))} Simulator"
        ),
    ),
    (
        re.compile(r"^pyemscripten_(\d+)_(\d+)_wasm32$"),
        lambda m: f"PyEmscripten {m.group(1)}.{m.group(2)} wasm32",
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


# Map known Python tags, ABI tags, Platform tags to labels.
_PLATFORM_MAP = {
    "win": [
        (re.compile(r"^win_(.*?)$"), lambda m: f"Windows {_norm_arch(m.group(1))}")
    ],
    "win32": [(re.compile(r"^win32$"), lambda m: "Windows x86")],
    "manylinux": [
        (
            re.compile(r"^manylinux_(\d+)_(\d+)_(.*?)$"),
            lambda m: (
                f"linux glibc {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))}"
            ),
        )
    ],
    "manylinux2014": [
        (
            re.compile(r"^manylinux2014_(.*?)$"),
            lambda m: f"linux glibc 2.17+ {_norm_arch(m.group(1))}",
        )
    ],
    "manylinux2010": [
        (
            re.compile(r"^manylinux2010_(.*?)$"),
            lambda m: f"linux glibc 2.12+ {_norm_arch(m.group(1))}",
        )
    ],
    "manylinux1": [
        (
            re.compile(r"^manylinux1_(.*?)$"),
            lambda m: f"linux glibc 2.5+ {_norm_arch(m.group(1))}",
        )
    ],
    "musllinux": [
        (
            re.compile(r"^musllinux_(\d+)_(\d+)_(.*?)$"),
            lambda m: f"linux musl {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))}",
        )
    ],
    "macosx": [
        (
            re.compile(r"^macosx_(\d+)_(\d+)_(.*?)$"),
            lambda m: f"macOS {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))}",
        )
    ],
    "ios": [
        (
            re.compile(r"^ios_(\d+)_(\d+)_(.*?)_iphoneos$"),
            lambda m: f"iOS {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))} Device",
        ),
        (
            re.compile(r"^ios_(\d+)_(\d+)_(.*?)_iphonesimulator$"),
            lambda m: (
                f"iOS {m.group(1)}.{m.group(2)}+ {_norm_arch(m.group(3))} Simulator"
            ),
        ),
    ],
    "android": [
        (
            re.compile(r"^android_(\d+)_(.*?)$"),
            lambda m: f"Android API level {m.group(1)}+ {_norm_arch(m.group(2))}",
        )
    ],
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
    return (s or "").replace("_", " ").strip()


def _implementation_to_label(raw: str) -> str:
    if raw.startswith("pypy"):
        version = _norm_str(raw.removeprefix("pypy"))
        return f"PyPy {version}"
    if raw.startswith("py"):
        major, minor = raw[2:3], raw[3:]
        return f"Python {major}{'.' if minor else ''}{minor}"
    if raw.startswith("cp"):
        version, suffixes = _format_cpython(raw.removeprefix("cp"))
        return f"CPython {version} {suffixes}".strip()
    if raw.startswith("pp"):
        version = _norm_str(raw.removeprefix("pp"))
        return f"PyPy {version}"
    if raw.startswith("ip"):
        major, minor = raw[2:3], raw[3:]
        return f"IronPython {major}{'.' if minor else ''}{minor}"
    if raw.startswith("jy"):
        major, minor = raw[2:3], raw[3:]
        version = f"{major}{'.' if minor else ''}{minor}"
        return f"Jython {version}"
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
    return version, " ".join(sorted(suffixes))


def _interpreter_to_label(tag: packaging.tags.Tag) -> str:
    return _implementation_to_label(tag.interpreter)


def _abi_to_label(tag: packaging.tags.Tag) -> str:
    if tag.abi == "none":
        return "(none)"
    if tag.abi == "abi3":
        # NOTE: CPython abi3 should have a CPython interpreter.
        # if not tag.interpreter.startswith("cp"):
        # A non- CPython interpreter with CPython abi3.
        # Should this be possible?
        # pass
        return "CPython abi3"
    if (
        tag.abi.startswith("cp")
        or tag.abi.startswith("pypy")
        or tag.abi.startswith("pp")
        or tag.abi.startswith("ip")
        or tag.abi.startswith("jy")
    ):
        return _implementation_to_label(tag.abi)
    # Unknown abi. Just return it.
    return _norm_str(tag.abi)


def _platform_to_label(tag: packaging.tags.Tag) -> str:
    if tag.platform == "any":
        return "(any)"

    value = tag.platform
    key = value.split("_", maxsplit=1)[0] if "_" in value else value

    patterns = _PLATFORM_MAP.get(key, [])
    for prefix_re, tmpl in patterns:
        if match := prefix_re.match(value):
            return tmpl(match)

    # Unknown platform. Just return it
    return _norm_str(value)


def _add_group_label(container: dict, group: str, value: str, label: str) -> None:
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
    for kind_items in grouped_labels.values():
        for label in kind_items.values():
            pretty_tags.add(label)
    return sorted(pretty_tags)


def filename_to_grouped_labels(filename: str) -> dict[str, dict[str, str]]:
    grouped_labels: dict[str, dict[str, str]] = {
        "interpreter": {},
        "abi": {},
        "platform": {},
        "other": {},
    }

    if filename.endswith(".egg"):
        grouped_labels["other"]["egg"] = "Egg"
        return grouped_labels
    if not filename.endswith(".whl"):
        grouped_labels["other"]["source"] = "Source"
        return grouped_labels

    tags = filename_to_tags(filename)
    for tag in tags:
        _add_group_label(
            grouped_labels, "interpreter", tag.interpreter, _interpreter_to_label(tag)
        )
        _add_group_label(grouped_labels, "abi", tag.abi, _abi_to_label(tag))
        _add_group_label(
            grouped_labels, "platform", tag.platform, _platform_to_label(tag)
        )
    return grouped_labels


def filenames_to_grouped_labels(filenames: list[str]) -> dict[str, dict[str, str]]:
    grouped_labels: dict[str, dict[str, str]] = {
        "interpreter": {},
        "abi": {},
        "platform": {},
        "other": {},
    }
    for filename in filenames:
        grouped = filename_to_grouped_labels(filename)
        for kind, kind_items in grouped.items():
            for value, label in kind_items.items():
                if value not in grouped_labels[kind]:
                    grouped_labels[kind][value] = label
    return grouped_labels


def _zip_filename_is_dir(filename: str) -> bool:
    """Return True if this ZIP archive member is a directory."""
    return filename.endswith(("/", "\\"))


def validate_record(wheel_filepath: str) -> bool:
    """
    Extract RECORD file from a wheel and check the ZIP archive contents
    against the files listed in the RECORD. Mismatches are reported via email.
    """
    filename = os.path.basename(wheel_filepath)
    name, version, _ = filename.split("-", 2)
    record_filename = f"{name}-{version}.dist-info/RECORD"
    # Files that must be missing from 'RECORD',
    # so we ignore them when cross-checking.
    record_exemptions = {
        f"{name}-{version}.dist-info/RECORD.jws",
        f"{name}-{version}.dist-info/RECORD.p7s",
    }
    try:
        with zipfile.ZipFile(wheel_filepath) as zfp:
            wheel_record_contents = zfp.read(record_filename).decode()
        record_entries = {
            fn.replace("\\", "/")  # Normalize Windows path separators.
            for fn, *_ in csv.reader(wheel_record_contents.splitlines())
        }
        wheel_entries = {
            fn
            for fn in zfp.namelist()
            if not _zip_filename_is_dir(fn) and fn not in record_exemptions
        }
    except UnicodeError, KeyError, csv.Error:
        raise MissingWheelRecordError
    if record_entries != wheel_entries:
        record_is_missing = wheel_entries - record_entries
        wheel_is_missing = record_entries - wheel_entries
        raise InvalidWheelRecordError(
            (f"Record is missing {record_is_missing})" if record_is_missing else "")
            + ("; " if record_is_missing and wheel_is_missing else "")
            + (f"Wheel is missing {wheel_is_missing})" if wheel_is_missing else "")
        )
    return True


# See: https://packaging.python.org/en/latest/specifications/entry-points/#data-model
_ENTRY_POINT_NAME_RE = re.compile(r"[\w.-]+")


def _validate_section(section: configparser.SectionProxy):
    """
    Validate the entry point names in a single section.
    """
    for ep_name in section:
        if _ENTRY_POINT_NAME_RE.fullmatch(ep_name) is None:
            raise InvalidWheelEntryPointsError(
                f"Invalid entry point name {ep_name!r} in {section.name!r}"
            )


def validate_entrypoints(wheel_filepath: str) -> bool:
    """
    Extract `entry_points.txt` from a wheel and check that it is valid.

    Current validity checks include being a well-formed INI file
    (matching the Entry Points specification's constraints) and
    that all `console_scripts` and `gui_scripts` entry points have names
    that do not contain absolute or relative path components.

    Validation errors are not currently reported via email.
    """

    # See: <https://packaging.python.org/en/latest/specifications/entry-points/#file-format>
    class CaseSensitiveConfigParser(configparser.ConfigParser):
        optionxform = staticmethod(str)  # type: ignore[assignment]

    filename = os.path.basename(wheel_filepath)
    name, version, _ = filename.split("-", 2)
    entry_points_filename = f"{name}-{version}.dist-info/entry_points.txt"

    # A wheel might not have an `entry_points.txt` file.
    try:
        with zipfile.ZipFile(wheel_filepath) as zfp:
            entry_points_contents = zfp.read(entry_points_filename).decode()
    except KeyError:
        return True
    except UnicodeError:
        # `entry_points.txt` must be decodable as UTF-8.
        raise InvalidWheelEntryPointsError("entry_points.txt is not decodable as UTF-8")

    # The Entry Points specification requires `=` as the delimiter.
    parser = CaseSensitiveConfigParser(delimiters=("=",))
    try:
        parser.read_string(entry_points_contents)
    except configparser.Error as error:
        raise InvalidWheelEntryPointsError(
            f"entry_points.txt is not a valid INI file: {error!r}"
        )

    for section_name in ("console_scripts", "gui_scripts"):
        try:
            section = parser[section_name]
        except KeyError:
            # `entry_points.txt` might not have these sections.
            continue
        _validate_section(section)

        # TODO: We could consider validating the entry point value as well.
        # See: https://packaging.python.org/en/latest/specifications/entry-points/#data-model

    return True


def main(argv) -> int:  # pragma: no cover
    if len(argv) != 1:
        print("Usage: python -m warehouse.utils.wheel <wheel path>")  # noqa: T201
        return 1
    wheel_filepath = argv[0]
    wheel_filename = os.path.basename(wheel_filepath)
    try:
        validate_record(wheel_filepath)
        validate_entrypoints(wheel_filepath)
        print(f"{wheel_filename}: OK")  # noqa: T201
        return 0
    except Exception as error:  # noqa: BLE001
        print(f"{wheel_filename}: {error!r}")  # noqa: T201
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
