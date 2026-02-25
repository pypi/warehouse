# SPDX-License-Identifier: Apache-2.0

import tarfile
import typing
import zipfile

from dataclasses import dataclass
from pathlib import Path

import structlog
import yara_x

logger = structlog.get_logger(__name__)

# YARA rules directory
_RULES_DIR = Path(__file__).parent / "scanner_rules"

# Extensions to scan inside archives
_SCAN_EXTENSIONS = {".py", ".pyc", ".pyd", ".so"}

# Max size of individual file to scan inside archive (5 MiB)
_SCAN_MAX_FILE_SIZE = 5 * 1024 * 1024


@dataclass(frozen=True)
class YaraMatch:
    rule: str  # Rule identifier, e.g. "pyarmor_encrypted"
    member: str  # Archive member path that triggered the match
    message: str  # User-facing message from rule metadata


def _get_rule_message(rule: yara_x.Rule) -> str:
    """Extract the ``message`` metadata from a matched YARA rule.

    All rules are required to have a ``message`` metadata field,
    enforced by ``test_all_rules_have_required_metadata``.
    """
    for key, value in rule.metadata:
        if key == "message":
            return value
    raise ValueError(  # pragma: no cover
        f"Rule {rule.identifier!r} is missing required 'message' metadata"
    )


def compile_rules(rules_dir: Path = _RULES_DIR) -> yara_x.Rules | None:
    """Compile all YARA rules from the rules directory.

    Returns None on failure (fail-open).
    """
    try:
        rule_files = sorted(rules_dir.glob("*.yar"))
        if not rule_files:
            logger.warning("No YARA rule files found", rules_dir=str(rules_dir))
            return None
        compiler = yara_x.Compiler()
        for rule_file in rule_files:
            compiler.add_source(rule_file.read_text())
        return compiler.build()
    except (OSError, yara_x.CompileError):
        logger.exception("Failed to compile YARA-X rules", exc_info=True)
        return None


# Module-level compiled rules (compiled once at import time)
_rules = compile_rules()


def iter_zip_members(zfp: zipfile.ZipFile) -> typing.Iterator[tuple[str, int, bytes]]:
    """Yield (name, size, data) for scannable files in a ZipFile."""
    for entry in zfp.infolist():
        if entry.is_dir():
            continue
        ext = Path(entry.filename).suffix.lower()
        if ext not in _SCAN_EXTENSIONS:
            continue
        yield entry.filename, entry.file_size, zfp.read(entry.filename)


def iter_tar_members(tar: tarfile.TarFile) -> typing.Iterator[tuple[str, int, bytes]]:
    """Yield (name, size, data) for scannable files in a TarFile."""
    for member in tar.getmembers():
        if not member.isfile():
            continue
        ext = Path(member.name).suffix.lower()
        if ext not in _SCAN_EXTENSIONS:
            continue
        f = tar.extractfile(member)
        if f is None:  # pragma: no cover
            continue
        yield member.name, member.size, f.read()


def check_members(
    members: typing.Iterable[tuple[str, int, bytes]],
    rules: yara_x.Rules | None = None,
    *,
    archive_name: str = "",
) -> YaraMatch | None:
    """Scan archive members and return the first YARA match.

    Returns ``YaraMatch`` on the first match, ``None`` otherwise.
    Fails open: returns ``None`` on scan errors.
    """
    rules = rules or _rules
    if rules is None:
        return None

    # Materialize members so we can do a bulk pre-scan.
    materialized: list[tuple[str, int, bytes]] = []
    bulk = bytearray()
    for name, size, data in members:
        if size > _SCAN_MAX_FILE_SIZE:
            logger.info(
                "Skipping oversized file in YARA scan",
                member=name,
                member_size=size,
                archive=archive_name,
                max_size=_SCAN_MAX_FILE_SIZE,
            )
            continue
        materialized.append((name, size, data))
        bulk.extend(data)

    yx_scanner = yara_x.Scanner(rules)
    try:
        # Fast path: scan all contents at once. If nothing matches,
        # skip per-file scanning entirely (the common case).
        if not yx_scanner.scan(bytes(bulk)).matching_rules:
            return None

        # Something matched — scan individual files for attribution.
        for name, _size, data in materialized:
            results = yx_scanner.scan(data)
            for matched_rule in results.matching_rules:
                return YaraMatch(
                    rule=matched_rule.identifier,
                    member=name,
                    message=_get_rule_message(matched_rule),
                )
    except yara_x.ScanError:
        logger.exception(
            "YARA-X scan failed",
            archive=archive_name,
            exc_info=True,
        )
        return None

    # Bulk scan matched across file boundaries but no individual file
    # triggered — a harmless false positive from concatenation.
    return None


def scan_archive(
    filename: str, rules: yara_x.Rules | None = None
) -> list[tuple[str, list[str]]]:
    """Open an archive and scan its members for YARA rule matches.

    Convenience wrapper for CLI use. The upload flow calls ``check_members``
    directly with an already-open archive.

    Returns empty list on no matches or on any failure (fail-open).

    Note: the scan loop here intentionally duplicates logic from
    ``check_members`` because the two have different return shapes —
    this collects *all* matching rule names per member, while
    ``check_members`` short-circuits on the first non-exempt match.
    """
    rules = rules or _rules
    if rules is None:
        return []

    archive_name = Path(filename).name
    yx_scanner = yara_x.Scanner(rules)
    matches: list[tuple[str, list[str]]] = []
    try:
        if filename.endswith((".zip", ".whl")):
            with zipfile.ZipFile(filename) as zfp:
                members = list(iter_zip_members(zfp))
        elif filename.endswith(".tar.gz"):
            with tarfile.open(filename, "r:gz") as tar:
                members = list(iter_tar_members(tar))
        else:
            return []

        # Filter out oversized files first.
        scannable: list[tuple[str, int, bytes]] = []
        for name, size, data in members:
            if size > _SCAN_MAX_FILE_SIZE:
                logger.info(
                    "Skipping oversized file in YARA scan",
                    member=name,
                    member_size=size,
                    archive=archive_name,
                    max_size=_SCAN_MAX_FILE_SIZE,
                )
                continue
            scannable.append((name, size, data))

        # Fast path: scan all contents at once. If nothing matches,
        # skip per-file scanning entirely (the common case).
        bulk = bytearray()
        for _, _, data in scannable:
            bulk.extend(data)
        if not yx_scanner.scan(bytes(bulk)).matching_rules:
            return []

        # Something matched — scan individual files for attribution.
        for name, _size, data in scannable:
            results = yx_scanner.scan(data)
            if results.matching_rules:
                matches.append((name, [r.identifier for r in results.matching_rules]))
    except (OSError, zipfile.BadZipFile, tarfile.TarError, yara_x.ScanError):
        logger.exception(
            "YARA-X scan failed",
            archive=archive_name,
            exc_info=True,
        )
        return []

    return matches


def main(argv: list[str]) -> int:  # pragma: no cover
    if len(argv) != 1:
        print("Usage: python -m warehouse.utils.scanner <archive path>")
        return 1
    filepath = argv[0]
    basename = Path(filepath).name
    matches = scan_archive(filepath)
    if not matches:
        print(f"{basename}: OK (no matches)")
    else:
        print(f"{basename}: MATCHED")
        for member, rule_names in matches:
            print(f"  {member}: {', '.join(rule_names)}")
    return 0 if not matches else 1


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
