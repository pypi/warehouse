# SPDX-License-Identifier: Apache-2.0

import hashlib

import pytest

from webob.multidict import MultiDict

from warehouse.forklift.forms import UploadForm


class TestUploadForm:
    _sha256 = hashlib.sha256().hexdigest()
    _blake2b = hashlib.blake2b(digest_size=32).hexdigest()

    @pytest.mark.parametrize(
        "data",
        [
            # Test for singular supported digests
            {"filetype": "sdist", "md5_digest": "bad"},
            {"filetype": "bdist_wheel", "pyversion": "3.4", "md5_digest": "bad"},
            {"filetype": "sdist", "sha256_digest": _sha256},
            {"filetype": "bdist_wheel", "pyversion": "3.4", "sha256_digest": _sha256},
            {"filetype": "sdist", "blake2_256_digest": _blake2b},
            {
                "filetype": "bdist_wheel",
                "pyversion": "3.4",
                "blake2_256_digest": _blake2b,
            },
            # Tests for multiple digests passing through
            {
                "filetype": "sdist",
                "md5_digest": "bad",
                "sha256_digest": _sha256,
                "blake2_256_digest": _blake2b,
            },
            {
                "filetype": "bdist_wheel",
                "pyversion": "3.4",
                "md5_digest": "bad",
                "sha256_digest": _sha256,
                "blake2_256_digest": _blake2b,
            },
        ],
    )
    def test_full_validate_valid(self, data):
        # `name` is required for any submission
        data["name"] = "fake-package"
        form = UploadForm(MultiDict(data))
        assert form.validate(), form.errors

    @pytest.mark.parametrize(
        "data",
        [
            {"filetype": "sdist", "pyversion": "3.4"},
            {"filetype": "bdist_wheel"},
            {"filetype": "bdist_wheel", "pyversion": "3.4"},
        ],
    )
    def test_full_validate_invalid(self, data):
        data["name"] = "fake-package"
        form = UploadForm(MultiDict(data))
        assert not form.validate()
