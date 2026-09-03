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


# Mapping from partial value to display names
# for platform, architecture, abi / implementation, CPython suffix, and file format.

_platform_display = {
    "any": "any",
    "win": "Windows",
    "win32": "Windows x86-32",
    "manylinux": "linux glibc",
    "manylinux2014": "linux glibc 2.17+",
    "manylinux2010": "linux glibc 2.12+",
    "manylinux1": "linux glibc 2.5+",
    "musllinux": "linux musl",
    "macosx": "macOS",
    "ios": "iOS",
    "iphoneos": "Device",
    "iphonesimulator": "Simulator",
    "android": "Android",
    "pyemscripten": "PyEmscripten",
}
_arch_display = {
    "amd64": "x86-64",
    "aarch64": "ARM64",
    "armeabi_v7a": "ARM EABI v7a",
    "arm64_v8a": "ARM64 v8a",
    "x86": "x86-32",
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
    "wasm32": "WebAssembly",
}
_impl_display = {
    "none": "none",
    "abi3": "abi3",
    "pypy": "PyPy",
    "py": "Python",
    "cp": "CPython",
    "pp": "PyPy",
    "ip": "IronPython",
    "jy": "Jython",
}
_cpython_suffix_display = {
    "d": "debug",
    "m": "pymalloc",
    "t": "free-threading",
    "u": "wide-unicode",
}
_file_format_display = {
    "egg": "Egg",
    "source": "Source",
}

# Wheel platform checking and display constants.

# Note: defining new platform ABI compatibility tags that don't
#       have a python.org binary release to anchor them is a
#       complex task that needs more than just OS+architecture info.
#       For Linux specifically, the platform ABI is defined by each
#       individual distro version, so wheels built on one version may
#       not even work on older versions of the same distro, let alone
#       a completely different distro.
#
#       That means new entries should only be added given an
#       accompanying ABI spec that explains how to build a
#       compatible binary (see the manylinux specs as examples).

# These platforms can be handled by a simple static list:
_allowed_platforms = {
    "any",
    "win32",
    "win_arm64",
    "win_amd64",
    "win_ia64",
    "manylinux1_x86_64",
    "manylinux1_i686",
    "manylinux2010_x86_64",
    "manylinux2010_i686",
    "manylinux2014_x86_64",
    "manylinux2014_i686",
    "manylinux2014_aarch64",
    "manylinux2014_armv7l",
    "manylinux2014_ppc64",
    "manylinux2014_ppc64le",
    "manylinux2014_s390x",
    "linux_armv6l",
    "linux_armv7l",
}

# macosx is a little more complicated:
_macosx_platform_re = re.compile(
    r"^(?P<plat>macosx)_(?P<major>\d+)_(?P<minor>\d+)_(?P<arch>.*)$"
)
_macosx_arches = {
    "ppc",
    "ppc64",
    "i386",
    "x86_64",
    "arm64",
    "intel",
    "fat",
    "fat3",
    "fat64",
    "universal",
    "universal2",
}
# macosx 10 is also supported, but with different rules
_macosx_major_versions = {
    "11",
    "12",
    "13",
    "14",
    "15",
    "26",
}

_ios_platform_re = re.compile(
    r"^(?P<plat>ios)_(?P<major>\d+)_(?P<minor>\d+)_(?P<arch>.*)_(?P<plat2>iphoneos|iphonesimulator)$"
)
_ios_arches = {
    "arm64",
    "x86_64",
}

_android_platform_re = re.compile(r"^(?P<plat>android)_(?P<major>\d+)_(?P<arch>.*)$")
_android_arches = {
    "armeabi_v7a",
    "arm64_v8a",
    "x86",
    "x86_64",
}

# manylinux pep600 and musllinux pep656 are a little more complicated:
_linux_platform_re = re.compile(
    r"^(?P<plat>(?P<libc>(many|musl))linux)_(?P<major>\d+)_(?P<minor>\d+)_(?P<arch>.*)$"
)
_jointlinux_arches = {
    "x86_64",
    "i686",
    "aarch64",
    "armv7l",
    "ppc64le",
    "s390x",
    "riscv64",
}
_manylinux_arches = _jointlinux_arches | {"ppc64"}
_musllinux_arches = _jointlinux_arches

_pyemscripten_platform_re = re.compile(
    r"^(?P<plat>pyemscripten)_(?P<major>\d+)_(?P<minor>\d+)_(?P<arch>wasm32)$"
)


def _format_version(s: str) -> str:
    s = (s or "").strip()
    length = len(s)
    if length <= 1:
        return s
    major, minor = s[0], s[1:]
    return f"{major}{'.' if minor else ''}{minor}"


def _norm_arch(a: str) -> str:
    return _arch_display.get(a, a)


def _norm_str(s: str) -> str:
    return (s or "").replace("_", " ").strip()


def _implementation_to_label(raw: str) -> str:
    if "_" in raw and (raw.startswith(("pypy", "pp"))):
        parts = [_implementation_to_label(i) for i in raw.split("_")]
        parts = [
            parts[0].strip(),
            *[
                p.split(" ", maxsplit=1)[1].strip() if " " in p else p.strip()
                for p in parts[1:]
            ],
        ]
        return " ".join(parts)
    if raw.startswith("pypy"):
        version = _norm_str(raw.removeprefix("pypy"))
        return f"{_impl_display['pypy']} {version}"
    if raw.startswith("pp"):
        version = _norm_str(raw.removeprefix("pp"))
        return f"{_impl_display['pp']} {version}"
    if raw.startswith("cp"):
        version, suffixes = _format_cpython(raw.removeprefix("cp"))
        return f"{_impl_display['cp']} {version} {suffixes}".strip()
    if raw.startswith("py"):
        version = _format_version(raw.removeprefix("py"))
        return f"{_impl_display['py']} {version}"
    if raw.startswith("ip"):
        version = _format_version(raw.removeprefix("ip"))
        return f"{_impl_display['ip']} {version}"
    if raw.startswith("jy"):
        version = _format_version(raw.removeprefix("jy"))
        return f"{_impl_display['jy']} {version}"
    # Unknown format. Normalise and return it.
    return _norm_str(raw)


def _format_cpython(s: str) -> tuple[str, str]:
    suffixes = []
    raw = (s or "").strip()
    while raw[-1].isalpha():
        last_char = raw[-1]
        name = _cpython_suffix_display.get(last_char)
        if not name:
            # Unknown CPython abi suffix. Just include it.
            name = last_char
        suffixes.append(name)
        raw = raw[0:-1]
    version = _format_version(raw)
    return version, " ".join(sorted(suffixes))


def _abi_to_label(tag: packaging.tags.Tag) -> str:
    key = tag.abi
    # TODO: Is abi3 required to be a CPython interpreter?
    #       tag.interpreter.startswith("cp")
    if key in ["none", "abi3"]:
        return _impl_display[key]
    if key.startswith(("cp", "pypy", "pp", "ip", "jy")):
        return _implementation_to_label(key)
    # Unknown abi. Just return it.
    return _norm_str(key)


def _parse_platform_tag(platform_tag) -> dict[str, str] | bool:
    """Check wheel platform is recognised and a valid combination.
    Return false if the platform tag is not valid.
    Return true if a static platform tag matches.
    Otherwise, return the valid parsed platform tag as a dict."""
    if platform_tag in _allowed_platforms:
        return True

    # All valid platform tags start with an identifier used for
    # building the displayed name.
    # Use this as an initial check that the platform tag might be valid.
    key = (
        platform_tag.split("_", maxsplit=1)[0] if "_" in platform_tag else platform_tag
    )
    if key not in _platform_display:
        return False

    m = _macosx_platform_re.match(platform_tag)
    # https://github.com/pypa/packaging.python.org/issues/1933
    # There's two macosx formats: `macosx_10_{minor}` for the 10.x series where
    # only the minor version ever increased, and `macosx_{major}_0` for the
    # new release scheme where we don't know how many minor versions each
    # release has.
    if m and m.group("major") == "10" and m.group("arch") in _macosx_arches:
        return m.groupdict()
    if (
        m
        and m.group("major") in _macosx_major_versions
        and m.group("minor") == "0"
        and m.group("arch") in _macosx_arches
    ):
        return m.groupdict()

    m = _linux_platform_re.match(platform_tag)
    if m and m.group("libc") == "musl" and m.group("arch") in _musllinux_arches:
        return m.groupdict()
    if m and m.group("libc") == "many" and m.group("arch") in _manylinux_arches:
        return m.groupdict()

    m = _ios_platform_re.match(platform_tag)
    if m and m.group("arch") in _ios_arches:
        return m.groupdict()

    m = _android_platform_re.match(platform_tag)
    if m and m.group("arch") in _android_arches:
        return m.groupdict()

    m = _pyemscripten_platform_re.match(platform_tag)
    if m:
        return m.groupdict()
    return False


def _platform_to_label(tag: packaging.tags.Tag) -> str:
    value = tag.platform
    parsed = _parse_platform_tag(value)

    if parsed is False or parsed is None:
        # Unknown platform, just return it.
        return _norm_str(value)

    if parsed is True:
        if "_" in value:
            # for static platform tags,
            # the value after the first underscore is the arch
            plat, arch = value.split("_", maxsplit=1)
            parsed = {"plat": plat, "arch": arch}
        else:
            parsed = {"plat": value}

    plat = parsed.get("plat") or ""
    major = parsed.get("major") or ""
    minor = parsed.get("minor") or ""
    arch = parsed.get("arch") or ""
    plat2 = parsed.get("plat2") or ""

    if plat in ["win", "manylinux2014", "manylinux2010", "manylinux1"]:
        return f"{_platform_display[plat]} {_norm_arch(arch)}"
    if plat in ["manylinux", "musllinux", "macosx", "pyemscripten"]:
        return f"{_platform_display[plat]} {major}.{minor}+ {_norm_arch(arch)}"
    if plat == "win32":
        return _platform_display[plat]
    if plat == "ios":
        return (
            f"{_platform_display[plat]} {major}.{minor}+ "
            f"{_norm_arch(arch)} {_platform_display[plat2]}"
        )
    if plat == "android":
        return f"{_platform_display[plat]} API level {major}+ {_norm_arch(arch)}"
    # Unknown platform. Just return it
    return _norm_str(value)


def _add_group_label(container: dict, group: str, value: str, label: str) -> None:
    container[group][value] = label


def _filename_to_tags(filename: str) -> set[packaging.tags.Tag]:
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

    # only include tags that restrict matches - these indicate no restriction
    pretty_tags.discard("any")
    pretty_tags.discard("none")

    return sorted(pretty_tags)


def filename_to_grouped_labels(filename: str) -> dict[str, dict[str, str]]:
    grouped_labels: dict[str, dict[str, str]] = {
        "interpreter": {},
        "abi": {},
        "platform": {},
        "other": {},
    }

    if filename.endswith(".egg"):
        _add_group_label(grouped_labels, "other", "egg", _file_format_display["egg"])
        return grouped_labels
    if not filename.endswith(".whl"):
        _add_group_label(
            grouped_labels, "other", "source", _file_format_display["source"]
        )
        return grouped_labels

    tags = _filename_to_tags(filename)
    for tag in tags:
        # Ignore implementation that is empty or all numbers.
        impl = _implementation_to_label(tag.interpreter)
        if impl and not all(c.isdigit() for c in impl):
            _add_group_label(grouped_labels, "interpreter", tag.interpreter, impl)

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


def is_valid_platform_tag(platform_tag) -> bool:
    """Check wheel platform is recognised and a valid combination."""
    parsed = _parse_platform_tag(platform_tag)
    return not (parsed is None or parsed is False)


def _zip_filename_is_dir(filename: str) -> bool:
    """Return True if this ZIP archive member is a directory."""
    return filename.endswith(("/", "\\"))


def _wheel_filename(archive: zipfile.ZipFile) -> str:
    if not isinstance(archive.filename, str):
        raise ValueError("An open wheel archive must be backed by a named file")
    return os.path.basename(archive.filename)


def _validate_record(archive: zipfile.ZipFile) -> bool:
    """
    Extract RECORD file from a wheel and check the ZIP archive contents
    against the files listed in the RECORD. Mismatches are reported via email.

    ``archive`` must be an open, named ``ZipFile``; it is not closed here.
    """
    filename = _wheel_filename(archive)
    name, version, _ = filename.split("-", 2)
    record_filename = f"{name}-{version}.dist-info/RECORD"
    # Files that must be missing from 'RECORD',
    # so we ignore them when cross-checking.
    record_exemptions = {
        f"{name}-{version}.dist-info/RECORD.jws",
        f"{name}-{version}.dist-info/RECORD.p7s",
    }
    try:
        wheel_record_contents = archive.read(record_filename).decode()
        record_entries = {
            fn.replace("\\", "/")  # Normalize Windows path separators.
            for fn, *_ in csv.reader(wheel_record_contents.splitlines())
        }
        wheel_entries = {
            fn
            for fn in archive.namelist()
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


def validate_record(wheel: str | zipfile.ZipFile) -> bool:
    if isinstance(wheel, zipfile.ZipFile):
        return _validate_record(wheel)
    with zipfile.ZipFile(wheel) as archive:
        return _validate_record(archive)


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


def _validate_entrypoints(archive: zipfile.ZipFile) -> bool:
    """
    Extract `entry_points.txt` from a wheel and check that it is valid.

    Current validity checks include being a well-formed INI file
    (matching the Entry Points specification's constraints) and
    that all `console_scripts` and `gui_scripts` entry points have names
    that do not contain absolute or relative path components.

    Validation errors are not currently reported via email.

    ``archive`` must be an open, named ``ZipFile``; it is not closed here.
    """

    # See: <https://packaging.python.org/en/latest/specifications/entry-points/#file-format>
    class CaseSensitiveConfigParser(configparser.ConfigParser):
        optionxform = staticmethod(str)  # type: ignore[assignment]

    filename = _wheel_filename(archive)
    name, version, _ = filename.split("-", 2)
    entry_points_filename = f"{name}-{version}.dist-info/entry_points.txt"

    # A wheel might not have an `entry_points.txt` file.
    try:
        entry_points_contents = archive.read(entry_points_filename).decode()
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


def validate_entrypoints(wheel: str | zipfile.ZipFile) -> bool:
    if isinstance(wheel, zipfile.ZipFile):
        return _validate_entrypoints(wheel)
    with zipfile.ZipFile(wheel) as archive:
        return _validate_entrypoints(archive)


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
