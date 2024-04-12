# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pretend
import pytest

from webob.multidict import MultiDict
from wtforms.validators import ValidationError

from warehouse.forklift.forms import UploadForm, _validate_pep440_version


class TestValidation:
    @pytest.mark.parametrize("version", ["1.0", "30a1", "1!1", "1.0-1", "v1.0"])
    def test_validates_valid_pep440_version(self, version):
        form, field = pretend.stub(), pretend.stub(data=version)
        _validate_pep440_version(form, field)

    @pytest.mark.parametrize("version", ["dog", "1.0.dev.a1"])
    def test_validates_invalid_pep440_version(self, version):
        form, field = pretend.stub(), pretend.stub(data=version)
        with pytest.raises(ValidationError):
            _validate_pep440_version(form, field)


class TestUploadForm:
    @pytest.mark.parametrize(
        "data",
        [
            # Test for singular supported digests
            {"filetype": "sdist", "md5_digest": "bad"},
            {"filetype": "bdist_wheel", "pyversion": "3.4", "md5_digest": "bad"},
            {"filetype": "sdist", "sha256_digest": "bad"},
            {"filetype": "bdist_wheel", "pyversion": "3.4", "sha256_digest": "bad"},
            {"filetype": "sdist", "blake2_256_digest": "bad"},
            {"filetype": "bdist_wheel", "pyversion": "3.4", "blake2_256_digest": "bad"},
            # Tests for multiple digests passing through
            {
                "filetype": "sdist",
                "md5_digest": "bad",
                "sha256_digest": "bad",
                "blake2_256_digest": "bad",
            },
            {
                "filetype": "bdist_wheel",
                "pyversion": "3.4",
                "md5_digest": "bad",
                "sha256_digest": "bad",
                "blake2_256_digest": "bad",
            },
        ],
    )
    def test_full_validate_valid(self, data):
        form = UploadForm(MultiDict(data))
        form.full_validate()

    @pytest.mark.parametrize(
        "data",
        [
            {"filetype": "sdist", "pyversion": "3.4"},
            {"filetype": "bdist_wheel"},
            {"filetype": "bdist_wheel", "pyversion": "3.4"},
        ],
    )
    def test_full_validate_invalid(self, data):
        form = UploadForm(MultiDict(data))
        with pytest.raises(ValidationError):
            form.full_validate()
