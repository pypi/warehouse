# SPDX-License-Identifier: Apache-2.0

import io
import struct
import zipfile

import pytest

from warehouse.utils import zipfiles


def extra_field(extra_id, data=b""):
    return struct.pack("<HH", extra_id, len(data)) + data


def local_header(extra, *, compressed_size=0, file_size=0):
    return (
        struct.pack(
            "<xxHHxxxxxxxxLLHH", 0, 0, compressed_size, file_size, 1, len(extra)
        )
        + b"a"
        + extra
    )


ORDINARY_EXTRA = extra_field(0x4321, b"metadata")


@pytest.mark.parametrize(
    ("extra", "compressed_size", "file_size"),
    [
        (ORDINARY_EXTRA + ORDINARY_EXTRA, 0, 0),
        (ORDINARY_EXTRA + extra_field(0x0001) + ORDINARY_EXTRA, 0, 0),
        (
            ORDINARY_EXTRA + extra_field(0x0001, struct.pack("<Q", 0)) + ORDINARY_EXTRA,
            0xFFFFFFFF,
            0xFFFFFFFF,
        ),
        (
            ORDINARY_EXTRA
            + extra_field(0x0001, struct.pack("<QQ", 0, 0))
            + ORDINARY_EXTRA,
            0xFFFFFFFF,
            0xFFFFFFFF,
        ),
        (
            ORDINARY_EXTRA
            + extra_field(0x0001, struct.pack("<QQQ", 0, 0, 7))
            + ORDINARY_EXTRA,
            0xFFFFFFFF,
            0xFFFFFFFF,
        ),
        (
            ORDINARY_EXTRA
            + extra_field(0x0001, struct.pack("<QQQL", 0, 0, 7, 2))
            + ORDINARY_EXTRA,
            0xFFFFFFFF,
            0xFFFFFFFF,
        ),
        (ORDINARY_EXTRA + extra_field(0x7075, b"\x01") + ORDINARY_EXTRA, 0, 0),
        (
            ORDINARY_EXTRA
            + extra_field(0x7075, b"\x01\x00\x00\x00\x00a")
            + ORDINARY_EXTRA,
            0,
            0,
        ),
    ],
)
def test_extra_fields_at_nonzero_offsets(extra, compressed_size, file_size):
    data = local_header(extra, compressed_size=compressed_size, file_size=file_size)
    fp = io.BytesIO(data)

    assert zipfiles._handle_local_file_header(fp, {"a": (0, 0)}) == b"a"
    assert fp.tell() == len(data)


@pytest.mark.parametrize(
    ("extra", "error"),
    [
        (
            extra_field(0x0001) + ORDINARY_EXTRA + extra_field(0x0001),
            "Invalid duplicate extra in local file",
        ),
        (
            extra_field(0x7075, b"\x01")
            + ORDINARY_EXTRA
            + extra_field(0x7075, b"\x01"),
            "Invalid duplicate extra in local file",
        ),
        (
            extra_field(0x0001) + ORDINARY_EXTRA + struct.pack("<HH", 0x0001, 10),
            "Malformed zip file",
        ),
        (ORDINARY_EXTRA + b"x", "Malformed zip file"),
        (ORDINARY_EXTRA + struct.pack("<HH", 0x4321, 10) + b"x", "Malformed zip file"),
        (ORDINARY_EXTRA + extra_field(0x0001, b"x"), "Malformed zip file"),
        (
            ORDINARY_EXTRA + extra_field(0x7075, b"\x01\x00\x00\x00\x00\xff"),
            "Filename not valid UTF-8",
        ),
        (
            ORDINARY_EXTRA + extra_field(0x7075, b"\x01\x00\x00\x00\x00\x7f"),
            "Invalid character in filename",
        ),
    ],
)
def test_invalid_extra_fields_at_nonzero_offsets(extra, error):
    data = local_header(extra)
    fp = io.BytesIO(data)

    with pytest.raises(zipfiles.InvalidZipFileError) as excinfo:
        zipfiles._handle_local_file_header(fp, {"a": (0, 0)})
    assert str(excinfo.value) == error
    assert fp.tell() == len(data)


class SliceTrackedBytes(bytes):
    """Count bytes returned by slices, rather than timings or specific APIs."""

    def __new__(cls, value, reader):
        result = super().__new__(cls, value)
        result.reader = reader
        return result

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if isinstance(key, slice):
            self.reader.sliced_bytes += len(value)
            return type(self)(value, self.reader)
        return value


class SliceTrackingReader(io.BytesIO):
    sliced_bytes = 0

    def read(self, size=-1):
        return SliceTrackedBytes(super().read(size), self)


@pytest.mark.parametrize("field_count", [16, 64, 256])
def test_extra_field_slice_work_is_linear(field_count):
    extra = extra_field(0x4321) * field_count
    fp = SliceTrackingReader(local_header(extra))

    assert zipfiles._handle_local_file_header(fp, {"a": (0, 0)}) == b"a"
    # This bounds slice output only, not all allocations or CPU work. The generous
    # budget allows copying individual fields, but not every remaining suffix.
    assert fp.sliced_bytes <= 4 * len(extra)


@pytest.mark.parametrize(
    ("extra", "result"),
    [
        (ORDINARY_EXTRA + extra_field(0x0001) + ORDINARY_EXTRA, (True, None)),
        (
            extra_field(0x0001) + ORDINARY_EXTRA + extra_field(0x0001),
            (False, "Invalid duplicate extra in local file"),
        ),
    ],
)
def test_archive_extra_fields_preserve_framing_and_stream_position(extra, result):
    data = io.BytesIO()
    info = zipfile.ZipInfo("a")
    info.extra = extra
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(info, b"data")

    with zipfile.ZipFile(data) as archive:
        archive.fp.seek(1)
        assert zipfiles.validate_zipfile(archive) == result
        assert archive.fp.tell() == 1
