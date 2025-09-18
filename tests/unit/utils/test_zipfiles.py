# SPDX-License-Identifier: Apache-2.0

import io
import os
import pathlib
import struct

import pytest

from warehouse.forklift.legacy import _is_valid_dist_file
from warehouse.utils import zipfiles

ZIPDATA_DIR = pathlib.Path(__file__).absolute().parent / "zipdata"


def zippath(filename: str):
    return str(ZIPDATA_DIR / filename)


@pytest.mark.parametrize(
    ("filename", "error"),
    [
        ("reject/8bitcomment.zip", "Filename not in central directory"),
        ("reject/cd_extra_entry.zip", "Duplicate filename in central directory"),
        ("reject/cd_missing_entry.zip", "Filename not in central directory"),
        ("reject/data_descriptor_bad_crc_0.zip", "Unknown record signature"),
        ("reject/dupe_eocd.zip", "Truncated central directory"),
        (
            "reject/eocd64_locator_mismatch.zip",
            "Mis-matched EOCD64 record and locator offset",
        ),
        ("reject/eocd64_non_locator.zip", "Malformed zip file"),
        ("reject/eocd64_without_eocd.zip", "Malformed zip file"),
        ("reject/eocd64_without_locator.zip", "Malformed zip file"),
        ("reject/missing_local_file.zip", "Missing filename in local headers"),
        ("reject/extra3byte.zip", "Malformed zip file"),
        ("reject/non_ascii_original_name.zip", "Filename not unicode"),
        ("reject/not.zip", "File is not a zip file"),
        ("reject/prefix.zip", "Unknown record signature"),
        ("reject/second_unicode_extra.zip", "Filename not in central directory"),
        ("reject/shortextra.zip", "Corrupt extra field 7075 (size=9)"),
        ("reject/suffix_not_comment.zip", "Trailing data"),
        ("reject/unicode_extra_chain.zip", "Filename not in central directory"),
        ("reject/wheel-1.0-py3-none-any.whl", "Duplicate filename in local headers"),
        ("reject/zip64_eocd_confusion.zip", "Filename not in central directory"),
        ("reject/zip64_eocd_extensible_data.zip", "Bad offset for central directory"),
        ("reject/zip64_extra_csize.zip", "Malformed zip file"),
        ("reject/zip64_extra_too_long.zip", "Mis-matched data size"),
        (
            "reject/zip64_extra_too_short.zip",
            "Corrupt zip64 extra field. Compress size not found.",
        ),
        ("reject/zip64_extra_usize.zip", "Malformed zip file"),
        ("reject/zipinzip.zip", "Filename not in central directory"),
    ],
)
def test_bad_zips(filename, error):
    result = zipfiles.validate_zipfile(zippath(filename))
    assert result[0] is False, error
    assert result[1] == error

    # Also test as a ZIP provided as a dist
    # is rejected if uploaded. The message
    # might be different, as this function
    # also checks ZIP validity.
    result = _is_valid_dist_file(zippath(filename), "sdist")
    assert result[0] is False


@pytest.mark.parametrize("filename", list(os.listdir(ZIPDATA_DIR / "accept")))
def test_good_zips(filename):
    result = zipfiles.validate_zipfile(zippath(f"accept/{filename}"))
    assert result[0] is True
    assert result[1] is None


def test_local_file_header():
    # Positive case!
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0, 1, 0)
    fp = io.BytesIO(header + b"a")
    filename = zipfiles._handle_local_file_header(fp, {"a": 0})
    assert filename == b"a"


def test_local_file_header_long_filename():
    # Filename too long
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0, 100, 0)
    fp = io.BytesIO(header + b"a")
    with pytest.raises(zipfiles.InvalidZipFileError):
        zipfiles._handle_local_file_header(fp, {"a": 0})


def test_local_file_header_compressed_length_mismatch_with_cd():
    # Mis-matched compressed data length
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0, 1, 0)
    fp = io.BytesIO(header + b"a")
    with pytest.raises(zipfiles.InvalidZipFileError):
        zipfiles._handle_local_file_header(fp, {"a": 1})


def test_local_file_header_short_extra():
    # Short extra
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0, 1, 3)
    fp = io.BytesIO(header + b"aeee")
    with pytest.raises(zipfiles.InvalidZipFileError):
        zipfiles._handle_local_file_header(fp, {"a": 0})


def test_local_file_header_invalid_extra_length():
    # Bad extra length
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0xFFFFFFFF, 1, 4)
    extra = struct.pack("<HH", 0x0001, 100)
    fp = io.BytesIO(header + b"a" + extra)
    with pytest.raises(zipfiles.InvalidZipFileError):
        zipfiles._handle_local_file_header(fp, {"a": 0})


def test_local_file_header_invalid_zip64_extra_data_length():
    # Bad extra data length
    extra = struct.pack("<HH", 0x0001, 1) + b"xxxxxxxx"
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0xFFFFFFFF, 1, len(extra))
    fp = io.BytesIO(header + b"a" + extra)
    with pytest.raises(zipfiles.InvalidZipFileError):
        zipfiles._handle_local_file_header(fp, {"a": 0})


def test_local_file_header_zip64_extra_no_compressed_size():
    # ZIP64, but compressed size missing from extra
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0xFFFFFFFF, 1, 4)
    extra = struct.pack("<HH", 0x0001, 0)
    fp = io.BytesIO(header + b"a" + extra)
    with pytest.raises(zipfiles.InvalidZipFileError):
        zipfiles._handle_local_file_header(fp, {"a": 0})


def test_local_file_header_zip64_extra_no_compressed_size_ok_using_store():
    # ZIP64 but without compressed size, but using 'STORE' compression
    # method. This means we can use 'uncompressed size' in extra.
    extra = struct.pack("<HHQ", 0x0001, 8, 1)
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0xFFFFFFFF, 1, len(extra))
    fp = io.BytesIO(header + b"a" + extra + b"a")
    filename = zipfiles._handle_local_file_header(fp, {"a": 1})
    assert filename == b"a"


def test_local_file_header_zip64_extra_no_compressed_size_nok_using_deflate():
    # ZIP64 but without compressed size, but using 'DEFLATE' compression
    # so we can't use uncompressed size: error!
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0x0009, 0xFFFFFFFF, 1, 12)
    extra = struct.pack("<HHQ", 0x0001, 0, 1)
    fp = io.BytesIO(header + b"a" + extra + b"a")
    with pytest.raises(zipfiles.InvalidZipFileError):
        zipfiles._handle_local_file_header(fp, {"a": 0})
