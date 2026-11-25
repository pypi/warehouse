# SPDX-License-Identifier: Apache-2.0

import contextlib
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

# Extensions and filenames to scan inside archives.
_SCAN_TARGETS = {
    # Python source for source-level rules (e.g. pyarmor)
    ".py",
    # .pye for SourceDefender-encrypted files
    ".pye",
    # Different textual files for common places where PyPI tokens are accidentally left.
    ".md",
    ".rst",
    ".env",
    ".txt",
    ".pypirc",
    ".toml",
    ".cfg",
    ".conf",
    # Popular script extensions
    ".sh",
    ".bash",
    ".ksh",
    ".zsh",
    ".bat",
    ".cmd",
    ".ps1",
    ".mk",  # Makefile extensions
    # All names are lowercased for case-insensitive matching
    # which can only improve the detection
    "makefile",
    "metadata",
    "pkg-info",
}

# Max size of individual file to scan inside archive (5 MiB). The iterators
# below stop reading an oversized member at the limit and yield it without
# data; see ``_read_scannable`` for how the limit bounds the read itself.
_SCAN_MAX_FILE_SIZE = 5 * 1024 * 1024

# Max total scannable content for bulk pre-scan optimization (50 MiB).
# Archives exceeding this fall back to per-file scanning to avoid
# holding multiple copies of all file contents in memory.
_BULK_SCAN_MAX_TOTAL = 50 * 1024 * 1024


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
        compiler.define_global("filename", "")
        for rule_file in rule_files:
            compiler.add_source(rule_file.read_text())
        return compiler.build()
    except OSError, yara_x.CompileError:
        logger.exception("Failed to compile YARA-X rules")
        return None


# Module-level compiled rules (compiled once at import time)
_rules = compile_rules()


def _should_scan_member(path: Path) -> bool:
    """Check if a member path is scannable based on its extension or name."""
    ext = path.suffix.lower()
    return (
        ext in _SCAN_TARGETS
        # Names like "METADATA", ".env" have empty suffix
        or path.name.lower() in _SCAN_TARGETS
    )


def _read_scannable(
    fp: typing.IO[bytes], *, member: str, declared_size: int, archive: str
) -> bytes | None:
    """Read a member's contents, or return ``None`` if it is over the size cap.

    Reads one byte past the cap rather than up to it: an oversized member then
    measures strictly larger than the cap, instead of looking like it exactly
    fits and getting scanned truncated.

    We decide on the number of bytes actually returned, never on
    ``declared_size``, since a crafted header can claim any size. That cuts
    both ways: a header that *under* declares its size still truncates what we
    see, because both ``zipfile`` and ``tarfile`` stop reading there. Because
    they stop there, the declared size can safely shrink the read request,
    which keeps ``tarfile`` from allocating the whole cap for a small member.
    It is also logged to keep a magnitude for triage.

    ``zipfile`` compares a member's CRC-32 only at end of member, which this
    read never reaches for an oversized one; ``iter_zip_members`` drains the
    rest so a corrupt payload is still rejected.
    """
    data = fp.read(min(declared_size, _SCAN_MAX_FILE_SIZE) + 1)
    if len(data) > _SCAN_MAX_FILE_SIZE:
        logger.info(
            "Skipping oversized file in YARA scan",
            member=member,
            declared_member_size=declared_size,
            archive=archive,
            max_size=_SCAN_MAX_FILE_SIZE,
        )
        return None
    return data


def iter_zip_members(
    zfp: zipfile.ZipFile, *, archive_name: str = ""
) -> typing.Iterator[tuple[str, int, bytes | None]]:
    """Yield (name, size, data) for scannable files in a ZipFile.

    An oversized member is yielded with ``data`` of ``None`` and a ``size`` of
    the cap plus one, so callers can count it without scanning it.

    Opens each entry rather than reading by name: an archive can carry several
    entries under one name, and ``ZipFile.read(name)`` resolves all of them to
    the last one in the central directory, leaving the earlier payloads
    unscanned. Uploads reject duplicate names before the scan, but
    ``scan_archive`` does not.
    """
    for entry in zfp.infolist():
        if entry.is_dir():
            continue
        path = Path(entry.filename)
        if not _should_scan_member(path):
            continue
        with zfp.open(entry) as fp:
            data = _read_scannable(
                fp,
                member=entry.filename,
                declared_size=entry.file_size,
                archive=archive_name,
            )
            if data is None:
                # Drain in capped chunks so zipfile still verifies the CRC-32.
                while fp.read(_SCAN_MAX_FILE_SIZE):
                    pass
        if data is None:
            yield entry.filename, _SCAN_MAX_FILE_SIZE + 1, None
            continue
        yield entry.filename, len(data), data


def iter_tar_members(
    tar: tarfile.TarFile, *, archive_name: str = ""
) -> typing.Iterator[tuple[str, int, bytes | None]]:
    """Yield (name, size, data) for scannable files in a TarFile.

    An oversized member is yielded as in ``iter_zip_members``.
    """
    for member in tar.getmembers():
        if not member.isfile():
            continue
        path = Path(member.name)
        if not _should_scan_member(path):
            continue
        f = tar.extractfile(member)
        if f is None:  # pragma: no cover
            continue
        with f:
            data = _read_scannable(
                f,
                member=member.name,
                declared_size=member.size,
                archive=archive_name,
            )
        if data is None:
            yield member.name, _SCAN_MAX_FILE_SIZE + 1, None
            continue
        yield member.name, len(data), data


def _timed_scan(yx_scanner, data, *, metrics, check_type, filename: str | None = None):
    """Run a single YARA scan and time it under ``warehouse.upload.yara.check``.

    ``check_type`` identifies which path the scan is on so we can tell which
    one is slow: ``bulk`` (whole-archive prescan), ``per_file_overflow``
    (file-at-a-time when archive exceeds the bulk cap), or
    ``per_file_attribution`` (file-at-a-time after a bulk match, to attribute
    which member triggered).
    """
    timer = (
        metrics.timed(
            "warehouse.upload.yara.check",
            tags=[f"check_type:{check_type}"],
        )
        if metrics is not None
        else contextlib.nullcontext()
    )
    with timer:
        # No rule uses the variable
        with contextlib.suppress(ValueError):
            yx_scanner.set_global("filename", filename or "")
        return yx_scanner.scan(data)


def check_members(
    members: typing.Iterable[tuple[str, int, bytes | None]],
    rules: yara_x.Rules | None = None,
    *,
    archive_name: str = "",
    archive_type: str = "unknown",
    metrics=None,
) -> YaraMatch | None:
    """Scan archive members and return the first YARA match.

    Returns ``YaraMatch`` on the first match, ``None`` otherwise.
    Fails open: returns ``None`` on scan errors.

    If ``metrics`` is provided, the whole scan (member read + YARA match) is
    timed under ``warehouse.upload.yara.scan``, tagged with ``archive_type``.
    This is the single umbrella metric for all YARA work per upload; emitting
    it here ensures every caller of the scanner gets it for free. The bytes
    and member count scanned, and the number of oversized members skipped,
    go to ``warehouse.upload.yara.bytes``, ``.members`` and ``.skipped``.
    ``.largest_member`` is the biggest member seen; the iterators stop reading
    at the cap, so an oversized member counts as the cap plus one.
    A ``yara_x.ScanError`` increments ``warehouse.upload.yara.error``.
    """
    rules = rules or _rules
    if rules is None:
        return None

    timer_cm = (
        metrics.timed(
            "warehouse.upload.yara.scan",
            tags=[f"archive_type:{archive_type}"],
        )
        if metrics is not None
        else contextlib.nullcontext()
    )

    yx_scanner = yara_x.Scanner(rules)
    materialized: list[tuple[str, int, bytes]] = []
    total_size = 0
    overflow = False
    scanned_bytes = scanned_members = skipped_members = largest_member = 0

    try:
        with timer_cm:
            for name, size, data in members:
                largest_member = max(largest_member, size)
                if data is None:
                    skipped_members += 1
                    continue

                scanned_bytes += len(data)
                scanned_members += 1

                if overflow:
                    # Over the size cap — scan each file individually.
                    results = _timed_scan(
                        yx_scanner,
                        data,
                        metrics=metrics,
                        check_type="per_file_overflow",
                        filename=name,
                    )
                    for matched_rule in results.matching_rules:
                        return YaraMatch(
                            rule=matched_rule.identifier,
                            member=name,
                            message=_get_rule_message(matched_rule),
                        )
                    continue

                materialized.append((name, size, data))
                total_size += len(data)

                if total_size > _BULK_SCAN_MAX_TOTAL:
                    overflow = True
                    # Exceeded size cap — scan materialized files individually.
                    for m_name, _, m_data in materialized:
                        results = _timed_scan(
                            yx_scanner,
                            m_data,
                            metrics=metrics,
                            check_type="per_file_overflow",
                            filename=m_name,
                        )
                        for matched_rule in results.matching_rules:
                            return YaraMatch(
                                rule=matched_rule.identifier,
                                member=m_name,
                                message=_get_rule_message(matched_rule),
                            )
                    materialized.clear()

            if not overflow:
                # Under the size cap — use bulk pre-scan optimization.
                bulk = b"".join(data for _, _, data in materialized)
                bulk_results = _timed_scan(
                    yx_scanner, bulk, metrics=metrics, check_type="bulk"
                )
                if not bulk_results.matching_rules:
                    return None
                # Something matched — scan individual files for attribution.
                for name, _size, data in materialized:
                    results = _timed_scan(
                        yx_scanner,
                        data,
                        metrics=metrics,
                        check_type="per_file_attribution",
                        filename=name,
                    )
                    for matched_rule in results.matching_rules:
                        return YaraMatch(
                            rule=matched_rule.identifier,
                            member=name,
                            message=_get_rule_message(matched_rule),
                        )
                # Bulk matched across file boundaries but no individual file
                # triggered — a harmless false positive from concatenation.
                return None

    except yara_x.ScanError:
        logger.exception("YARA-X scan failed", archive=archive_name)
        if metrics is not None:
            metrics.increment(
                "warehouse.upload.yara.error", tags=[f"archive_type:{archive_type}"]
            )
        return None
    finally:
        if metrics is not None:
            tags = [f"archive_type:{archive_type}"]
            metrics.histogram("warehouse.upload.yara.bytes", scanned_bytes, tags)
            metrics.histogram("warehouse.upload.yara.members", scanned_members, tags)
            metrics.histogram(
                "warehouse.upload.yara.largest_member", largest_member, tags
            )
            if skipped_members:
                metrics.increment(
                    "warehouse.upload.yara.skipped", skipped_members, tags
                )

    # Overflow path completed with no matches found.
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
    ``check_members`` short-circuits on the first match.
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
                members = list(iter_zip_members(zfp, archive_name=archive_name))
        elif filename.endswith(".tar.gz"):
            with tarfile.open(filename, "r:gz") as tar:
                members = list(iter_tar_members(tar, archive_name=archive_name))
        else:
            return []
        scannable = [(name, data) for name, _, data in members if data is not None]

        # Fast path: if total scannable content is under the size cap,
        # scan all contents at once. If nothing matches, skip per-file
        # scanning entirely (the common case).
        total_size = sum(len(data) for _, data in scannable)
        if total_size <= _BULK_SCAN_MAX_TOTAL:
            bulk = b"".join(data for _, data in scannable)
            if not yx_scanner.scan(bulk).matching_rules:
                return []

        # Either the bulk scan matched, or we're over the size cap —
        # scan individual files.
        for name, data in scannable:
            # No rule uses the variable
            with contextlib.suppress(ValueError):
                yx_scanner.set_global("filename", name)
            results = yx_scanner.scan(data)
            if results.matching_rules:
                matches.append((name, [r.identifier for r in results.matching_rules]))
    except OSError, zipfile.BadZipFile, tarfile.TarError, yara_x.ScanError:
        logger.exception("YARA-X scan failed", archive=archive_name)
        return []

    return matches


def main(argv: list[str]) -> int:  # pragma: no cover
    if len(argv) != 1:
        print("Usage: python -m warehouse.utils.scanner <archive path>")  # noqa: T201
        return 1
    filepath = argv[0]
    basename = Path(filepath).name
    matches = scan_archive(filepath)
    if not matches:
        print(f"{basename}: OK (no matches)")  # noqa: T201
    else:
        print(f"{basename}: MATCHED")  # noqa: T201
        for member, rule_names in matches:
            print(f"  {member}: {', '.join(rule_names)}")  # noqa: T201
    return 0 if not matches else 1


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
