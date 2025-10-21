# SPDX-License-Identifier: Apache-2.0

import os
import struct
import sys
import typing
import zipfile

RECORD_SIG_CENTRAL_DIRECTORY = b"\x50\x4b\x01\x02"
RECORD_SIG_LOCAL_FILE = b"\x50\x4b\x03\x04"
RECORD_SIG_EOCD = b"\x50\x4b\x05\x06"
RECORD_SIG_EOCD64 = b"\x50\x4b\x06\x06"
RECORD_SIG_EOCD64_LOCATOR = b"\x50\x4b\x06\x07"
RECORD_SIG_DATA_DESCRIPTOR = b"\x50\x4b\x07\x08"

# Extras that shouldn't be duplicated.
DISALLOW_DUPLICATE_EXTRA_IDS = {
    0x0001,  # ZIP64 extended info
    0x7075,  # Info-ZIP Unicode Path
}
# Unprintable characters we disallow from filenames.
UNPRINTABLE_CHARS = set(range(0x00, 0x20)) | {0x7F}


class InvalidZipFileError(Exception):
    """Internal exception used by this module"""


def _seek_check(fp: typing.IO[bytes], amt: int, /) -> None:
    """Call seek and check that the seeked amount
    is correct. Returns True if the seeked amount
    is less than what is expected.
    """
    if amt < 0:  # pragma: no cover
        raise InvalidZipFileError("Negative offset")
    fp.seek(amt, os.SEEK_CUR)


def _read_check(fp: typing.IO[bytes], amt: int, /) -> bytes:
    """Read and assert there was enough data available."""
    if amt < 0:  # pragma: no cover
        raise InvalidZipFileError("Negative offset")
    data = fp.read(amt)
    if len(data) != amt:
        raise InvalidZipFileError("Malformed zip file")
    return data


def _contains_unprintable_chars(value: bytes) -> bool:
    return any(ch in UNPRINTABLE_CHARS for ch in value)


def _handle_local_file_header(
    fp: typing.IO[bytes], zipfile_files_and_sizes: dict[str, int]
) -> bytes:
    """
    Parses the body of a Local File header. Returns
    the contained filename field of the record.

    See section 4.3.7 of APPNOTE.TXT.
    """
    data = _read_check(fp, 26)
    gpbf, compress_method, compressed_size, filename_size, extra_size = struct.unpack(
        "<xxHHxxxxxxxxLxxxxHH", data
    )
    filename = _read_check(fp, filename_size)
    extra = _read_check(fp, extra_size)

    if _contains_unprintable_chars(filename):
        raise InvalidZipFileError("Invalid character in filename")

    # Search for the ZIP64 extension in extras.
    seen_extra_ids = set()
    while extra:
        if len(extra) < 4:
            raise InvalidZipFileError("Malformed zip file")
        extra_id, extra_data_size = struct.unpack("<HH", extra[:4])
        if extra_data_size + 4 > len(extra):
            raise InvalidZipFileError("Malformed zip file")
        if extra_id in seen_extra_ids and extra_id in DISALLOW_DUPLICATE_EXTRA_IDS:
            raise InvalidZipFileError("Invalid duplicate extra in local file")
        seen_extra_ids.add(extra_id)

        if extra_id == 0x0001:

            # ZIP64 extras must be one of these lengths.
            if extra_data_size not in (0, 8, 16, 24, 28):
                raise InvalidZipFileError("Malformed zip file")

            # This is a ZIP64 archive, but the file size is
            # less than 0xFFFFFFFF, so we use the compressed
            # size from the record itself.
            if extra_data_size == 0:
                if compressed_size == 0xFFFFFFFF:
                    raise InvalidZipFileError("Malformed zip file")

            # We only have uncompressed size, so we have to
            # double-check that we're NOT using compression
            # so we know that compressed and uncompressed
            # data sizes are the same.
            elif extra_data_size == 8:
                if compress_method != 0x0000:  # "STORE" method
                    raise InvalidZipFileError("Malformed zip file")
                # Use uncompressed size, the first field in the extra data.
                (compressed_size,) = struct.unpack("<Q", extra[4:12])

            else:
                # We receive an explicit compressed ZIP64 size.
                # This is the second field in the extra data.
                (compressed_size,) = struct.unpack("<Q", extra[12:20])

        elif extra_id == 0x7075:
            # Info ZIP Unicode Path Extra layout
            # 0x7075        2 bytes
            # TSize         2 bytes
            # Version       1 byte
            # NameCRC32     4 bytes
            # UnicodeName   TSize - 5
            unicode_name = extra[9 : 4 + extra_data_size]
            if _contains_unprintable_chars(unicode_name):
                raise InvalidZipFileError("Invalid character in filename")
            try:
                unicode_name.decode("utf-8")
            except UnicodeError:
                raise InvalidZipFileError("Filename not valid UTF-8")

        extra = extra[extra_data_size + 4 :]

    # If the local file is using streaming mode then
    # use the compression size from central directory.
    has_data_descriptor = gpbf & 0x08
    if has_data_descriptor:
        raise InvalidZipFileError("ZIP contains a data descriptor")
    try:
        filename_as_str = filename.decode("utf-8")
        if zipfile_files_and_sizes[filename_as_str] != compressed_size:
            raise InvalidZipFileError("Mis-matched data size")
    except UnicodeError:
        raise InvalidZipFileError("Filename not unicode")
    except KeyError:
        raise InvalidZipFileError("Filename not in central directory")

    _seek_check(fp, compressed_size)

    return filename


def _handle_central_directory_header(fp: typing.IO[bytes]) -> tuple[bytes, bytes]:
    """
    Parses the body of a Central Directory (CD) header.
    Returns the contained filename field of the record.

    See section 4.3.12 of APPNOTE.TXT.
    """
    data = _read_check(fp, 42)
    compressed_size, filename_size, extra_size, comment_size, offset = struct.unpack(
        "<xxxxxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", data
    )
    if comment_size != 0:
        raise InvalidZipFileError("Comment in central directory")
    filename = _read_check(fp, filename_size)
    extra = _read_check(fp, extra_size)

    if _contains_unprintable_chars(filename):
        raise InvalidZipFileError("Invalid character in filename")

    return filename, extra


def _handle_eocd(fp: typing.IO[bytes]) -> tuple[int, int, int]:
    """
    Parses the body of an End of Central Directory (EOCD) record.

    See section 4.3.16 of APPNOTE.TXT.
    """
    data = _read_check(fp, 18)
    (
        cd_records_on_disk,
        cd_records,
        cd_size,
        cd_offset,
        comment_size,
    ) = struct.unpack("<xxxxHHLLH", data)
    if cd_records_on_disk != cd_records:
        raise InvalidZipFileError("Malformed zip file")
    _seek_check(fp, comment_size)
    return cd_records, cd_size, cd_offset


def _handle_eocd64(fp: typing.IO[bytes]) -> tuple[int, int, int]:
    """
    Parses the body of an ZIP64 End of Central Directory (EOCD64) record.

    See section 4.3.14 of APPNOTE.TXT.
    """
    data = _read_check(fp, 52)
    (eocd64_size, cd_records_on_disk, cd_records, cd_size, cd_offset) = struct.unpack(
        "<QxxxxxxxxxxxxQQQQ", data
    )
    if cd_records_on_disk != cd_records:
        raise InvalidZipFileError("Malformed zip file")
    _seek_check(fp, eocd64_size - 44)
    return cd_records, cd_size, cd_offset


def _handle_eocd64_locator(fp: typing.IO[bytes]) -> int:
    """
    Parses the body of an ZIP64 End of Central Directory Locator record.

    See section 4.3.15 of APPNOTE.TXT.
    """
    data = _read_check(fp, 16)
    (eocd64_offset,) = struct.unpack("<xxxxQxxxx", data)
    return eocd64_offset


def validate_zipfile(zip_filepath: str) -> tuple[bool, str | None]:
    """
    Validates that a ZIP file would parse the same through
    a ZIP implementation that checks the Central Directory
    and an implementation that streams Local File headers
    without checking the Central Directory (CD).

    This is done mostly by ensuring there are no duplicate
    or mismatched files between Local Files and CD.

    Implemented using the ZIP standard (APPNOTE.TXT):
    https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
    """

    # Process the zipfile through Python's
    # zipfile processor, the same used by
    # pip and other Python installers.
    try:
        zfp = zipfile.ZipFile(zip_filepath, mode="r")
        # Store compression sizes from the CD for use later.
        zipfile_files = {zfi.orig_filename: zfi.compress_size for zfi in zfp.filelist}
    except zipfile.BadZipfile as e:
        return False, e.args[0]

    with open(zip_filepath, mode="rb") as fp:
        # Track filenames that have been seen in
        # Local File and Central Directory headers
        # to avoid duplicates or missing entries.
        local_filenames = set()
        cd_filenames = set()

        # These variables enforce the requirements
        # of EOCD for ZIP64. ZIP64 has its own EOCD
        # record, but that record may be followed by
        # a EOCD64 Locator and/or a '0xFF'-filled
        # non-ZIP64 EOCD record.
        expected_eocd64_offset = None
        actual_eocd64_offset = None

        # Track the number of CD records
        # and their sizes.
        cd_records = 0
        cd_offset = None
        cd_size = 0

        # Values from EOCD or EOCD64.
        eocd_cd_records = None
        eocd_cd_offset = None
        eocd_cd_size = None

        while True:
            try:
                signature = _read_check(fp, 4)

                # Only accept EOCD after an EOCD64 if we've
                # seen the EOCD64 Locator first.
                if (
                    signature == RECORD_SIG_EOCD
                    and expected_eocd64_offset is not None
                    and actual_eocd64_offset is None
                ):
                    return False, "Malformed zip file"

                # Only accept a single EOCD64 Locator after EOCD64.
                if signature == RECORD_SIG_EOCD64_LOCATOR and (
                    expected_eocd64_offset is None or actual_eocd64_offset is not None
                ):
                    return False, "Malformed zip file"

                # If we've seen an EOCD64 record then we only
                # accept an EOCD64 Locator or an EOCD.
                if (
                    signature not in (RECORD_SIG_EOCD64_LOCATOR, RECORD_SIG_EOCD)
                    and expected_eocd64_offset is not None
                ):
                    return False, "Malformed zip file"

                # Central Directory File Header
                if signature == RECORD_SIG_CENTRAL_DIRECTORY:
                    # Record the first CD record we find as
                    # the start of the central directory.
                    if cd_offset is None:
                        cd_offset = fp.tell() - 4
                    cd_records += 1

                    filename, extra = _handle_central_directory_header(fp)
                    cd_size += 46 + len(filename) + len(extra)
                    if filename in cd_filenames:
                        raise InvalidZipFileError(
                            "Duplicate filename in central directory"
                        )
                    if filename not in local_filenames:
                        raise InvalidZipFileError("Missing filename in local headers")
                    cd_filenames.add(filename)

                # Local File Header
                elif signature == RECORD_SIG_LOCAL_FILE:
                    filename = _handle_local_file_header(fp, zipfile_files)
                    if filename in local_filenames:
                        raise InvalidZipFileError("Duplicate filename in local headers")
                    local_filenames.add(filename)

                # End of Central Directory
                elif signature == RECORD_SIG_EOCD:
                    # If the ZIP is empty then we expect
                    # to see zero CD entries.
                    if cd_offset is None:
                        cd_offset = fp.tell() - 4

                    # If this archive is ZIP64 we use the values
                    # from the EOCD64 values, otherwise use EOCD values.
                    if actual_eocd64_offset is not None and eocd_cd_offset is not None:
                        _handle_eocd(fp)
                    else:
                        eocd_cd_records, eocd_cd_size, eocd_cd_offset = _handle_eocd(fp)

                    if eocd_cd_records != cd_records:
                        raise InvalidZipFileError(
                            "Mismatched central directory records"
                        )
                    if cd_offset is None or eocd_cd_offset != cd_offset:
                        raise InvalidZipFileError("Mismatched central directory offset")
                    # This branch is tough to cover, as CPython's ZIP archive
                    # implementation already doesn't like mismatches between size
                    # and offset of the CD.
                    if cd_size is None or eocd_cd_size != cd_size:  # pragma: no cover
                        raise InvalidZipFileError("Mismatched central directory size")

                    break  # This always means the end of a ZIP.

                # End of Central Directory (ZIP64)
                elif signature == RECORD_SIG_EOCD64:
                    # We cross-check this value if
                    # we see EOCD64 Locator later.
                    # -4 because we just read signature bytes.
                    expected_eocd64_offset = fp.tell() - 4
                    eocd_cd_records, eocd_cd_size, eocd_cd_offset = _handle_eocd64(fp)

                # End of Central Directory (ZIP64) Locator
                elif signature == RECORD_SIG_EOCD64_LOCATOR:
                    actual_eocd64_offset = _handle_eocd64_locator(fp)

                    # Cross-check the offset specified in the EOCD64 Locator
                    # record with the one we ourselves recorded earlier.
                    if (
                        expected_eocd64_offset is None
                        or expected_eocd64_offset != actual_eocd64_offset
                    ):
                        return False, "Mis-matched EOCD64 record and locator offset"

                # Note that there are other record types,
                # but I didn't find any on PyPI, and they don't
                # seem relevant to Python packaging use-case
                # ie: encrypted ZIP files. So maybe we want
                # to reject these anyway?
                else:
                    return False, "Unknown record signature"

            except InvalidZipFileError as e:
                return False, e.args[0]

        # Defensive, this shouldn't be possible in regular operation.
        if cd_filenames != local_filenames:  # pragma: no cover
            return False, "Mis-matched local headers and central directory"

        # Detect whether there is trailing data
        # after the end of the zip file.
        # This can indicate ZIP files that are
        # concatenated together.
        cur = fp.tell()
        fp.seek(0, os.SEEK_END)
        if cur != fp.tell():
            return False, "Trailing data"

    return True, None


def main(argv) -> int:  # pragma: no cover
    if len(argv) != 1:
        print("Usage: python -m warehouse.utils.zipfiles <ZIP path>")
        return 1
    zip_filepath = argv[0]
    zip_filename = os.path.basename(zip_filepath)
    ok, error = validate_zipfile(zip_filepath)
    if ok:
        print(f"{zip_filename}: OK")
    else:
        print(f"{zip_filename}: {error}")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
