# SPDX-License-Identifier: Apache-2.0

import io
import os
import pathlib
import struct
import tempfile

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
        ("reject/data_descriptor.zip", "ZIP contains a data descriptor"),
        ("reject/data_descriptor_bad_crc.zip", "ZIP contains a data descriptor"),
        ("reject/data_descriptor_bad_crc_0.zip", "ZIP contains a data descriptor"),
        ("reject/data_descriptor_bad_csize.zip", "ZIP contains a data descriptor"),
        ("reject/data_descriptor_bad_usize.zip", "ZIP contains a data descriptor"),
        (
            "reject/data_descriptor_bad_usize_no_sig.zip",
            "ZIP contains a data descriptor",
        ),
        ("reject/data_descriptor_zip64.zip", "ZIP contains a data descriptor"),
        ("reject/data_descriptor_zip64_csize.zip", "ZIP contains a data descriptor"),
        ("reject/data_descriptor_zip64_usize.zip", "ZIP contains a data descriptor"),
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
        ("reject/second_unicode_extra.zip", "Invalid duplicate extra in local file"),
        ("reject/shortextra.zip", "Corrupt extra field 7075 (size=9)"),
        ("reject/suffix_not_comment.zip", "Trailing data"),
        ("reject/unicode_extra_chain.zip", "Invalid duplicate extra in local file"),
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
    assert result[0] is True, f"Expected no error, got {result[1]!r}"
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


def test_local_file_invalid_filename():
    header = struct.pack("<xxHHxxxxxxxxLxxxxHxx", 0, 0, 0xFFFFFFFF, 1)
    fp = io.BytesIO(header + b"\x7f")
    with pytest.raises(zipfiles.InvalidZipFileError) as e:
        zipfiles._handle_local_file_header(fp, {"a": 0})
    assert str(e.value) == "Invalid character in filename"


def test_local_file_invalid_filename_in_unicode_extra():
    extra = struct.pack("<HHxxxxxxxx", 0x7075, 8)
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0, 1, len(extra))
    fp = io.BytesIO(header + b"a" + extra)
    with pytest.raises(zipfiles.InvalidZipFileError) as e:
        zipfiles._handle_local_file_header(fp, {"a": 0})
    assert str(e.value) == "Invalid character in filename"


def test_local_file_invalid_filename_utf8():
    extra = struct.pack("<HHxxxxx", 0x7075, 6) + b"\xf7"
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0, 1, len(extra))
    fp = io.BytesIO(header + b"a" + extra)
    with pytest.raises(zipfiles.InvalidZipFileError) as e:
        zipfiles._handle_local_file_header(fp, {"a": 0})
    assert str(e.value) == "Filename not valid UTF-8"


def test_local_file_multiple_extras():
    extras = struct.pack("<HH", 0x7075, 1) + b"a" + struct.pack("<HHxxxx", 0x0002, 4)
    header = struct.pack("<xxHHxxxxxxxxLxxxxHH", 0, 0, 0, 1, len(extras))
    fp = io.BytesIO(header + b"a" + extras)
    filename = zipfiles._handle_local_file_header(fp, {"a": 0})
    assert filename == b"a"


def test_cd_with_comment_rejected():
    data = struct.pack("<xxxxxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", 0, 1, 0, 1, 0)
    fp = io.BytesIO(data)
    with pytest.raises(zipfiles.InvalidZipFileError) as e:
        zipfiles._handle_central_directory_header(fp)
    assert str(e.value) == "Comment in central directory"


def test_cd_with_invalid_filename():
    data = struct.pack("<xxxxxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", 0, 1, 0, 0, 0) + b"\x00"
    fp = io.BytesIO(data)
    with pytest.raises(zipfiles.InvalidZipFileError) as e:
        zipfiles._handle_central_directory_header(fp)
    assert str(e.value) == "Invalid character in filename"


def test_eocd_mismatched_records_on_disk():
    data = struct.pack("<xxxxHHLLH", 100, 1, 0, 0, 0)
    fp = io.BytesIO(data)
    with pytest.raises(zipfiles.InvalidZipFileError) as e:
        zipfiles._handle_eocd(fp)
    assert str(e.value) == "Malformed zip file"


def test_eocd64_mismatched_records_on_disk():
    data = struct.pack("<QxxxxxxxxxxxxQQQQ", 0, 100, 1, 0, 0)
    fp = io.BytesIO(data)
    with pytest.raises(zipfiles.InvalidZipFileError) as e:
        zipfiles._handle_eocd64(fp)
    assert str(e.value) == "Malformed zip file"


def test_cd_and_eocd_match():
    data_lf = (
        zipfiles.RECORD_SIG_LOCAL_FILE
        + struct.pack("<xxHHHxxxxxxLxxxxHH", 0, 0, 20, 0, 1, 0)
        + b"a"
    )
    data_cd = (
        zipfiles.RECORD_SIG_CENTRAL_DIRECTORY
        + struct.pack("<HHxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", 20, 20, 0, 1, 0, 0, 0)
        + b"a"
    )
    cd_records = 1
    cd_offset = len(data_lf)
    cd_size = len(data_cd)
    data_eocd = zipfiles.RECORD_SIG_EOCD + struct.pack(
        "<xxxxHHLLH", cd_records, cd_records, cd_size, cd_offset, 0
    )
    data = data_lf + data_cd + data_eocd
    with tempfile.NamedTemporaryFile(mode="wb") as tmp:
        tmp.write(data)
        tmp.flush()
        assert (True, None) == zipfiles.validate_zipfile(tmp.name)


@pytest.mark.parametrize(
    ("cd_records", "error"),
    [
        (0, "Mismatched central directory records"),
        (2, "Mismatched central directory records"),
    ],
)
def test_cd_and_eocd_mismatch_records(cd_records, error):
    data_lf = (
        zipfiles.RECORD_SIG_LOCAL_FILE
        + struct.pack("<xxHHHxxxxxxLxxxxHH", 0, 0, 20, 0, 1, 0)
        + b"a"
    )
    data_cd = (
        zipfiles.RECORD_SIG_CENTRAL_DIRECTORY
        + struct.pack("<HHxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", 20, 20, 0, 1, 0, 0, 0)
        + b"a"
    )
    cd_offset = len(data_lf)
    cd_size = len(data_cd)
    data_eocd = zipfiles.RECORD_SIG_EOCD + struct.pack(
        "<xxxxHHLLH", cd_records, cd_records, cd_size, cd_offset, 0
    )
    data = data_lf + data_cd + data_eocd
    with tempfile.NamedTemporaryFile(mode="wb") as tmp:
        tmp.write(data)
        tmp.flush()
        assert (False, error) == zipfiles.validate_zipfile(tmp.name)


@pytest.mark.parametrize(
    ("cd_offset_diff", "error"),
    [
        (-1, "Mismatched central directory offset"),
        (1, "Mismatched central directory offset"),
    ],
)
def test_cd_and_eocd_mismatch_offset(cd_offset_diff, error):
    data_lf = (
        zipfiles.RECORD_SIG_LOCAL_FILE
        + struct.pack("<xxHHHxxxxxxLxxxxHH", 0, 0, 20, 0, 1, 0)
        + b"a"
    )
    data_cd = (
        zipfiles.RECORD_SIG_CENTRAL_DIRECTORY
        + struct.pack("<HHxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", 20, 20, 0, 1, 0, 0, 0)
        + b"a"
    )
    cd_records = 1
    cd_offset = len(data_lf) + cd_offset_diff
    cd_size = len(data_cd)
    data_eocd = zipfiles.RECORD_SIG_EOCD + struct.pack(
        "<xxxxHHLLH", cd_records, cd_records, cd_size, cd_offset, 0
    )
    data = data_lf + data_cd + data_eocd
    with tempfile.NamedTemporaryFile(mode="wb") as tmp:
        tmp.write(data)
        tmp.flush()
        assert (False, error) == zipfiles.validate_zipfile(tmp.name)


@pytest.mark.parametrize(
    ("cd_size_diff", "error"),
    [
        (-1, "Bad magic number for central directory"),
        (1, "Bad magic number for central directory"),
    ],
)
def test_cd_and_eocd_mismatch_size(cd_size_diff, error):
    data_lf = (
        zipfiles.RECORD_SIG_LOCAL_FILE
        + struct.pack("<xxHHHxxxxxxLxxxxHH", 0, 0, 20, 0, 1, 0)
        + b"a"
    )
    data_cd = (
        zipfiles.RECORD_SIG_CENTRAL_DIRECTORY
        + struct.pack("<HHxxxxxxxxxxxxLxxxxHHHxxxxxxxxL", 20, 20, 0, 1, 0, 0, 0)
        + b"a"
    )
    cd_records = 1
    cd_offset = len(data_lf)
    cd_size = len(data_cd) + cd_size_diff
    data_eocd = zipfiles.RECORD_SIG_EOCD + struct.pack(
        "<xxxxHHLLH", cd_records, cd_records, cd_size, cd_offset, 0
    )
    data = data_lf + data_cd + data_eocd
    with tempfile.NamedTemporaryFile(mode="wb") as tmp:
        tmp.write(data)
        tmp.flush()
        assert (False, error) == zipfiles.validate_zipfile(tmp.name)
