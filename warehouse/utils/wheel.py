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
    if not filename.endswith(".whl"):
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
