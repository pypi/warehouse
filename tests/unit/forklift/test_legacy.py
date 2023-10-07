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

import hashlib
import io
import re
import tarfile
import tempfile
import zipfile

from cgi import FieldStorage
from unittest import mock

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPTooManyRequests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from trove_classifiers import classifiers
from webob.multidict import MultiDict
from wtforms.form import Form
from wtforms.validators import ValidationError

from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.classifiers.models import Classifier
from warehouse.errors import BasicAuthTwoFactorEnabled
from warehouse.forklift import legacy
from warehouse.metrics import IMetricsService
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.utils import OIDCContext
from warehouse.packaging.interfaces import IFileStorage, IProjectService
from warehouse.packaging.models import (
    Dependency,
    DependencyKind,
    File,
    Filename,
    JournalEntry,
    Project,
    Release,
    Role,
)
from warehouse.packaging.tasks import sync_file_to_cache, update_bigquery_release_files
from warehouse.utils.security_policy import AuthenticationMethod

from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.classifiers import ClassifierFactory
from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.packaging import (
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
)


def _get_tar_testdata(compression_type=""):
    temp_f = io.BytesIO()
    with tarfile.open(fileobj=temp_f, mode=f"w:{compression_type}") as tar:
        tar.add("/dev/null", arcname="fake_package/PKG-INFO")
    return temp_f.getvalue()


def _get_whl_testdata(name="fake_package", version="1.0"):
    temp_f = io.BytesIO()
    with zipfile.ZipFile(file=temp_f, mode="w") as zfp:
        zfp.writestr(f"{name}-{version}.dist-info/METADATA", "Fake metadata")
    return temp_f.getvalue()


def _storage_hash(data):
    return hashlib.blake2b(data, digest_size=256 // 8).hexdigest()


_TAR_GZ_PKG_TESTDATA = _get_tar_testdata("gz")
_TAR_GZ_PKG_MD5 = hashlib.md5(_TAR_GZ_PKG_TESTDATA).hexdigest()
_TAR_GZ_PKG_SHA256 = hashlib.sha256(_TAR_GZ_PKG_TESTDATA).hexdigest()
_TAR_GZ_PKG_STORAGE_HASH = _storage_hash(_TAR_GZ_PKG_TESTDATA)

_TAR_BZ2_PKG_TESTDATA = _get_tar_testdata("bz2")
_TAR_BZ2_PKG_MD5 = hashlib.md5(_TAR_BZ2_PKG_TESTDATA).hexdigest()
_TAR_BZ2_PKG_SHA256 = hashlib.sha256(_TAR_BZ2_PKG_TESTDATA).hexdigest()
_TAR_BZ2_PKG_STORAGE_HASH = _storage_hash(_TAR_BZ2_PKG_TESTDATA)


class TestExcWithMessage:
    def test_exc_with_message(self):
        exc = legacy._exc_with_message(HTTPBadRequest, "My Test Message.")
        assert isinstance(exc, HTTPBadRequest)
        assert exc.status_code == 400
        assert exc.status == "400 My Test Message."

    def test_exc_with_exotic_message(self):
        exc = legacy._exc_with_message(
            HTTPBadRequest, "look at these wild chars: аÃ¤â€—"
        )
        assert isinstance(exc, HTTPBadRequest)
        assert exc.status_code == 400
        assert exc.status == "400 look at these wild chars: ?Ã¤â??"


class TestValidation:
    @pytest.mark.parametrize("version", ["1.0", "30a1", "1!1", "1.0-1", "v1.0"])
    def test_validates_valid_pep440_version(self, version):
        form, field = pretend.stub(), pretend.stub(data=version)
        legacy._validate_pep440_version(form, field)

    @pytest.mark.filterwarnings("ignore:Creating a LegacyVersion.*:DeprecationWarning")
    @pytest.mark.parametrize("version", ["dog", "1.0.dev.a1", "1.0+local"])
    def test_validates_invalid_pep440_version(self, version):
        form, field = pretend.stub(), pretend.stub(data=version)
        with pytest.raises(ValidationError):
            legacy._validate_pep440_version(form, field)

    @pytest.mark.parametrize(
        ("requirement", "expected"),
        [("foo", ("foo", None)), ("foo (>1.0)", ("foo", ">1.0"))],
    )
    def test_parses_legacy_requirement_valid(self, requirement, expected):
        parsed = legacy._parse_legacy_requirement(requirement)
        assert parsed == expected

    @pytest.mark.parametrize("requirement", ["foo bar"])
    def test_parses_legacy_requirement_invalid(self, requirement):
        with pytest.raises(ValueError):
            legacy._parse_legacy_requirement(requirement)

    @pytest.mark.parametrize("specifier", [">=1.0", "<=1.0-1"])
    def test_validates_valid_pep440_specifier(self, specifier):
        legacy._validate_pep440_specifier(specifier)

    @pytest.mark.parametrize("specifier", ["wat?"])
    def test_validates_invalid_pep440_specifier(self, specifier):
        with pytest.raises(ValidationError):
            legacy._validate_pep440_specifier(specifier)

    @pytest.mark.parametrize(
        "requirement", ["foo (>=1.0)", "foo", "_foo", "foo2", "foo.bar"]
    )
    def test_validates_legacy_non_dist_req_valid(self, requirement):
        legacy._validate_legacy_non_dist_req(requirement)

    @pytest.mark.parametrize(
        "requirement",
        [
            "foo-bar (>=1.0)",
            "foo-bar",
            "2foo (>=1.0)",
            "2foo",
            "☃ (>=1.0)",
            "☃",
            "name @ https://github.com/pypa",
            "foo.2bar",
        ],
    )
    def test_validates_legacy_non_dist_req_invalid(self, requirement):
        with pytest.raises(ValidationError):
            legacy._validate_legacy_non_dist_req(requirement)

    def test_validate_legacy_non_dist_req_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(legacy, "_validate_legacy_non_dist_req", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        legacy._validate_legacy_non_dist_req_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]

    @pytest.mark.parametrize(
        "requirement",
        ["foo (>=1.0)", "foo", "foo2", "foo-bar", "foo_bar", "foo == 2.*"],
    )
    def test_validate_legacy_dist_req_valid(self, requirement):
        legacy._validate_legacy_dist_req(requirement)

    @pytest.mark.parametrize(
        "requirement",
        [
            "☃ (>=1.0)",
            "☃",
            "foo-",
            "foo- (>=1.0)",
            "_foo",
            "_foo (>=1.0)",
            "name @ https://github.com/pypa",
        ],
    )
    def test_validate_legacy_dist_req_invalid(self, requirement):
        with pytest.raises(ValidationError):
            legacy._validate_legacy_dist_req(requirement)

    def test_validate_legacy_dist_req_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(legacy, "_validate_legacy_dist_req", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        legacy._validate_legacy_dist_req_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]

    @pytest.mark.parametrize(
        ("requirement", "specifier"), [("C", None), ("openssl (>=1.0.0)", ">=1.0.0")]
    )
    def test_validate_requires_external(self, monkeypatch, requirement, specifier):
        spec_validator = pretend.call_recorder(lambda spec: None)
        monkeypatch.setattr(legacy, "_validate_pep440_specifier", spec_validator)

        legacy._validate_requires_external(requirement)

        if specifier is not None:
            assert spec_validator.calls == [pretend.call(specifier)]
        else:
            assert spec_validator.calls == []

    def test_validate_requires_external_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(legacy, "_validate_requires_external", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        legacy._validate_requires_external_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]

    @pytest.mark.parametrize(
        "project_url",
        [
            "Home, https://pypi.python.org/",
            "Home,https://pypi.python.org/",
            ("A" * 32) + ", https://example.com/",
        ],
    )
    def test_validate_project_url_valid(self, project_url):
        legacy._validate_project_url(project_url)

    @pytest.mark.parametrize(
        "project_url",
        [
            "https://pypi.python.org/",
            ", https://pypi.python.org/",
            "Home, ",
            ("A" * 33) + ", https://example.com/",
            "Home, I am a banana",
            "Home, ssh://foobar",
            "",
        ],
    )
    def test_validate_project_url_invalid(self, project_url):
        with pytest.raises(ValidationError):
            legacy._validate_project_url(project_url)

    @pytest.mark.parametrize(
        "project_urls",
        [["Home, https://pypi.python.org/", ("A" * 32) + ", https://example.com/"]],
    )
    def test_all_valid_project_url_list(self, project_urls):
        form, field = pretend.stub(), pretend.stub(data=project_urls)
        legacy._validate_project_url_list(form, field)

    @pytest.mark.parametrize(
        "project_urls",
        [
            ["Home, https://pypi.python.org/", ""],  # Valid  # Invalid
            [
                ("A" * 32) + ", https://example.com/",  # Valid
                ("A" * 33) + ", https://example.com/",  # Invalid
            ],
        ],
    )
    def test_invalid_member_project_url_list(self, project_urls):
        form, field = pretend.stub(), pretend.stub(data=project_urls)
        with pytest.raises(ValidationError):
            legacy._validate_project_url_list(form, field)

    def test_validate_project_url_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(legacy, "_validate_project_url", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        legacy._validate_project_url_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]

    @pytest.mark.parametrize(
        "data",
        [
            (""),
            ("foo@bar.com"),
            ("foo@bar.com,"),
            ("foo@bar.com, biz@baz.com"),
            ('"C. Schultz" <cschultz@example.com>'),
            ('"C. Schultz" <cschultz@example.com>, snoopy@peanuts.com'),
        ],
    )
    def test_validate_rfc822_email_field(self, data):
        form, field = pretend.stub(), pretend.stub(data=data)
        legacy._validate_rfc822_email_field(form, field)

    @pytest.mark.parametrize(
        "data",
        [
            ("foo"),
            ("foo@"),
            ("@bar.com"),
            ("foo@bar"),
            ("foo AT bar DOT com"),
            ("foo@bar.com, foo"),
        ],
    )
    def test_validate_rfc822_email_field_raises(self, data):
        form, field = pretend.stub(), pretend.stub(data=data)
        with pytest.raises(ValidationError):
            legacy._validate_rfc822_email_field(form, field)

    @pytest.mark.parametrize(
        "data",
        [
            "text/plain; charset=UTF-8",
            "text/x-rst; charset=UTF-8",
            "text/markdown; charset=UTF-8; variant=CommonMark",
            "text/markdown; charset=UTF-8; variant=GFM",
            "text/markdown",
        ],
    )
    def test_validate_description_content_type_valid(self, data):
        form, field = pretend.stub(), pretend.stub(data=data)
        legacy._validate_description_content_type(form, field)

    @pytest.mark.parametrize(
        "data",
        [
            "invalid_type/plain",
            "text/invalid_subtype",
            "text/plain; charset=invalid_charset",
            "text/markdown; charset=UTF-8; variant=invalid_variant",
        ],
    )
    def test_validate_description_content_type_invalid(self, data):
        form, field = pretend.stub(), pretend.stub(data=data)
        with pytest.raises(ValidationError):
            legacy._validate_description_content_type(form, field)

    def test_validate_no_deprecated_classifiers_valid(self, db_request):
        valid_classifier = ClassifierFactory(classifier="AA :: BB")

        form = pretend.stub()
        field = pretend.stub(data=[valid_classifier.classifier])

        legacy._validate_no_deprecated_classifiers(form, field)

    @pytest.mark.parametrize(
        "deprecated_classifiers", [({"AA :: BB": []}), ({"AA :: BB": ["CC :: DD"]})]
    )
    def test_validate_no_deprecated_classifiers_invalid(
        self, db_request, deprecated_classifiers, monkeypatch
    ):
        monkeypatch.setattr(legacy, "deprecated_classifiers", deprecated_classifiers)

        form = pretend.stub()
        field = pretend.stub(data=["AA :: BB"])

        with pytest.raises(ValidationError):
            legacy._validate_no_deprecated_classifiers(form, field)

    def test_validate_classifiers_valid(self, db_request, monkeypatch):
        monkeypatch.setattr(legacy, "classifiers", {"AA :: BB"})

        form = pretend.stub()
        field = pretend.stub(data=["AA :: BB"])

        legacy._validate_classifiers(form, field)

    @pytest.mark.parametrize("data", [(["AA :: BB"]), (["AA :: BB", "CC :: DD"])])
    def test_validate_classifiers_invalid(self, db_request, data):
        form = pretend.stub()
        field = pretend.stub(data=data)

        with pytest.raises(ValidationError):
            legacy._validate_classifiers(form, field)


def test_construct_dependencies():
    types = {"requires": DependencyKind.requires, "provides": DependencyKind.provides}

    form = pretend.stub(
        requires=pretend.stub(data=["foo (>1)"]),
        provides=pretend.stub(data=["bar (>2)"]),
    )

    for dep in legacy._construct_dependencies(form, types):
        assert isinstance(dep, Dependency)

        if dep.kind == DependencyKind.requires:
            assert dep.specifier == "foo (>1)"
        elif dep.kind == DependencyKind.provides:
            assert dep.specifier == "bar (>2)"
        else:
            pytest.fail("Unknown type of specifier")


class TestListField:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            (["foo", "bar"], ["foo", "bar"]),
            (["  foo"], ["foo"]),
            (["f oo  "], ["f oo"]),
            ("", []),
            (" ", []),
        ],
    )
    def test_processes_form_data(self, data, expected):
        field = legacy.ListField()
        field = field.bind(pretend.stub(meta=pretend.stub()), "formname")
        field.process_formdata(data)
        assert field.data == expected

    @pytest.mark.parametrize(("value", "expected"), [("", []), ("wutang", ["wutang"])])
    def test_coerce_string_into_list(self, value, expected):
        class MyForm(Form):
            test = legacy.ListField()

        form = MyForm(MultiDict({"test": value}))

        assert form.test.data == expected


class TestMetadataForm:
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
        form = legacy.MetadataForm(MultiDict(data))
        form.full_validate()

    @pytest.mark.parametrize(
        "data", [{"filetype": "sdist", "pyversion": "3.4"}, {"filetype": "bdist_wheel"}]
    )
    def test_full_validate_invalid(self, data):
        form = legacy.MetadataForm(MultiDict(data))
        with pytest.raises(ValidationError):
            form.full_validate()

    def test_requires_python(self):
        form = legacy.MetadataForm(MultiDict({"requires_python": ">= 3.5"}))
        form.requires_python.validate(form)


class TestFileValidation:
    def test_defaults_to_true(self):
        assert legacy._is_valid_dist_file("", "")

    @pytest.mark.parametrize(
        ("filename", "filetype"),
        [
            ("test.zip", "sdist"),
            ("test.whl", "bdist_wheel"),
        ],
    )
    def test_bails_with_invalid_zipfile(self, tmpdir, filename, filetype):
        f = str(tmpdir.join(filename))

        with open(f, "wb") as fp:
            fp.write(b"this isn't a valid zip file")

        assert not legacy._is_valid_dist_file(f, filetype)

    @pytest.mark.parametrize("filename", ["test.tar.gz"])
    def test_bails_with_invalid_tarfile(self, tmpdir, filename):
        fake_tar = str(tmpdir.join(filename))

        with open(fake_tar, "wb") as fp:
            fp.write(b"Definitely not a valid tar file.")

        assert not legacy._is_valid_dist_file(fake_tar, "sdist")

    @pytest.mark.parametrize("compression", ("gz",))
    def test_tarfile_validation_invalid(self, tmpdir, compression):
        file_extension = f".{compression}" if compression else ""
        tar_fn = str(tmpdir.join(f"test.tar{file_extension}"))
        data_file = str(tmpdir.join("dummy_data"))

        with open(data_file, "wb") as fp:
            fp.write(b"Dummy data file.")

        with tarfile.open(tar_fn, f"w:{compression}") as tar:
            tar.add(data_file, arcname="package/module.py")

        assert not legacy._is_valid_dist_file(
            tar_fn, "sdist"
        ), "no PKG-INFO; should fail"

    @pytest.mark.parametrize("compression", ("gz",))
    def test_tarfile_validation_valid(self, tmpdir, compression):
        file_extension = f".{compression}" if compression else ""
        tar_fn = str(tmpdir.join(f"test.tar{file_extension}"))
        data_file = str(tmpdir.join("dummy_data"))

        with open(data_file, "wb") as fp:
            fp.write(b"Dummy data file.")

        with tarfile.open(tar_fn, f"w:{compression}") as tar:
            tar.add(data_file, arcname="package/module.py")
            tar.add(data_file, arcname="package/PKG-INFO")
            tar.add(data_file, arcname="package/data_file.txt")

        assert legacy._is_valid_dist_file(tar_fn, "sdist")

    def test_zip_no_pkg_info(self, tmpdir):
        f = str(tmpdir.join("test.zip"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("something.txt", b"Just a placeholder file")

        assert not legacy._is_valid_dist_file(f, "sdist")

    def test_zip_has_pkg_info(self, tmpdir):
        f = str(tmpdir.join("test.zip"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("something.txt", b"Just a placeholder file")
            zfp.writestr("PKG-INFO", b"this is the package info")

        assert legacy._is_valid_dist_file(f, "sdist")

    def test_zipfile_supported_compression(self, tmpdir):
        f = str(tmpdir.join("test.zip"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("PKG-INFO", b"this is the package info")
            zfp.writestr("1.txt", b"1", zipfile.ZIP_STORED)
            zfp.writestr("2.txt", b"2", zipfile.ZIP_DEFLATED)

        assert legacy._is_valid_dist_file(f, "")

    @pytest.mark.parametrize("method", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
    def test_zipfile_unsupported_compression(self, tmpdir, method):
        f = str(tmpdir.join("test.zip"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("1.txt", b"1", zipfile.ZIP_STORED)
            zfp.writestr("2.txt", b"2", zipfile.ZIP_DEFLATED)
            zfp.writestr("3.txt", b"3", method)

        assert not legacy._is_valid_dist_file(f, "")

    def test_zipfile_exceeds_compression_threshold(self, tmpdir):
        f = str(tmpdir.join("test.zip"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("PKG-INFO", b"this is the package info")
            zfp.writestr("1.dat", b"0" * 65 * legacy.ONE_MB, zipfile.ZIP_DEFLATED)

        assert not legacy._is_valid_dist_file(f, "")

    def test_wheel_no_wheel_file(self, tmpdir):
        f = str(tmpdir.join("test.whl"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("something.txt", b"Just a placeholder file")

        assert not legacy._is_valid_dist_file(f, "bdist_wheel")

    def test_wheel_has_wheel_file(self, tmpdir):
        f = str(tmpdir.join("test.whl"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("something.txt", b"Just a placeholder file")
            zfp.writestr("WHEEL", b"this is the package info")

        assert legacy._is_valid_dist_file(f, "bdist_wheel")


class TestIsDuplicateFile:
    def test_is_duplicate_true(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }
        db_request.db.add(
            FileFactory.create(
                release=release,
                filename=filename,
                md5_digest=hashes["md5"],
                sha256_digest=hashes["sha256"],
                blake2_256_digest=hashes["blake2_256"],
                path="source/{name[0]}/{name}/{filename}".format(
                    name=project.name, filename=filename
                ),
            )
        )

        assert legacy._is_duplicate_file(db_request.db, filename, hashes)

    def test_is_duplicate_none(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        requested_file_name = f"{project.name}-{release.version}-1.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }
        db_request.db.add(
            FileFactory.create(
                release=release,
                filename=filename,
                md5_digest=hashes["md5"],
                sha256_digest=hashes["sha256"],
                blake2_256_digest=hashes["blake2_256"],
                path="source/{name[0]}/{name}/{filename}".format(
                    name=project.name, filename=filename
                ),
            )
        )

        hashes["blake2_256"] = "another blake2 digest"

        assert (
            legacy._is_duplicate_file(db_request.db, requested_file_name, hashes)
            is None
        )

    def test_is_duplicate_false_same_blake2(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        requested_file_name = f"{project.name}-{release.version}-1.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }
        db_request.db.add(
            FileFactory.create(
                release=release,
                filename=filename,
                md5_digest=hashes["md5"],
                sha256_digest=hashes["sha256"],
                blake2_256_digest=hashes["blake2_256"],
                path="source/{name[0]}/{name}/{filename}".format(
                    name=project.name, filename=filename
                ),
            )
        )

        assert (
            legacy._is_duplicate_file(db_request.db, requested_file_name, hashes)
            is False
        )

    def test_is_duplicate_false(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }

        wrong_hashes = {"sha256": "nah", "md5": "nope", "blake2_256": "nuh uh"}

        db_request.db.add(
            FileFactory.create(
                release=release,
                filename=filename,
                md5_digest=hashes["md5"],
                sha256_digest=hashes["sha256"],
                blake2_256_digest=hashes["blake2_256"],
                path="source/{name[0]}/{name}/{filename}".format(
                    name=project.name, filename=filename
                ),
            )
        )

        assert legacy._is_duplicate_file(db_request.db, filename, wrong_hashes) is False


class TestFileUpload:
    def test_fails_disallow_new_upload(self, pyramid_config, pyramid_request):
        pyramid_request.flags = pretend.stub(
            enabled=lambda value: value == AdminFlagValue.DISALLOW_NEW_UPLOAD
        )
        pyramid_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")
        pyramid_request.user = pretend.stub(primary_email=pretend.stub(verified=True))

        with pytest.raises(HTTPForbidden) as excinfo:
            legacy.file_upload(pyramid_request)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == (
            "403 New uploads are temporarily disabled. "
            "See /the/help/url/ for more information."
        )

    @pytest.mark.parametrize("version", ["2", "3", "-1", "0", "dog", "cat"])
    def test_fails_invalid_version(self, pyramid_config, pyramid_request, version):
        pyramid_request.POST["protocol_version"] = version
        pyramid_request.flags = pretend.stub(enabled=lambda *a: False)

        user = pretend.stub(primary_email=pretend.stub(verified=True))
        pyramid_config.testing_securitypolicy(identity=user)
        pyramid_request.user = user

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(pyramid_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Unknown protocol version."

    @pytest.mark.parametrize(
        ("post_data", "message"),
        [
            # metadata_version errors.
            (
                {},
                "'' is an invalid value for Metadata-Version. "
                "Error: This field is required. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            (
                {"metadata_version": "-1"},
                "'-1' is an invalid value for Metadata-Version. "
                "Error: Use a known metadata version. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            # name errors.
            (
                {"metadata_version": "1.2"},
                "'' is an invalid value for Name. "
                "Error: This field is required. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            (
                {"metadata_version": "1.2", "name": "foo-"},
                "'foo-' is an invalid value for Name. "
                "Error: Start and end with a letter or numeral containing "
                "only ASCII numeric and '.', '_' and '-'. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            # version errors.
            (
                {"metadata_version": "1.2", "name": "example"},
                "'' is an invalid value for Version. "
                "Error: This field is required. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            (
                {"metadata_version": "1.2", "name": "example", "version": "dog"},
                "'dog' is an invalid value for Version. "
                "Error: Start and end with a letter or numeral "
                "containing only ASCII numeric and '.', '_' and '-'. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            # filetype/pyversion errors.
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "md5_digest": "bad",
                },
                "Invalid value for filetype. Error: This field is required.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "bdist_wat",
                },
                "Error: Python version is required for binary distribution uploads.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "bdist_wat",
                    "pyversion": "1.0",
                    "md5_digest": "bad",
                },
                "Invalid value for filetype. Error: Use a known file type.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                    "pyversion": "1.0",
                },
                "Error: Use 'source' as Python version for an sdist.",
            ),
            # digest errors.
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                },
                "Error: Include at least one message digest.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                    "sha256_digest": "an invalid sha256 digest",
                },
                "Invalid value for sha256_digest. "
                "Error: Use a valid, hex-encoded, SHA256 message digest.",
            ),
            # summary errors
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                    "md5_digest": "a fake md5 digest",
                    "summary": "A" * 513,
                },
                "'"
                + "A" * 30
                + "..."
                + "A" * 30
                + "' is an invalid value for Summary. "
                "Error: Field cannot be longer than 512 characters. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                    "md5_digest": "a fake md5 digest",
                    "summary": "A\nB",
                },
                "{!r} is an invalid value for Summary. ".format("A\nB")
                + "Error: Use a single line only. "
                "See "
                "https://packaging.python.org/specifications/core-metadata"
                " for more information.",
            ),
            # classifiers are a FieldStorage
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                    "classifiers": FieldStorage(),
                },
                "classifiers: Should not be a tuple.",
            ),
            # keywords are a FieldStorage
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                    "keywords": FieldStorage(),
                },
                "keywords: Should not be a tuple.",
            ),
        ],
    )
    @pytest.mark.filterwarnings("ignore:Creating a LegacyVersion.*:DeprecationWarning")
    def test_fails_invalid_post_data(
        self, pyramid_config, db_request, post_data, message
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(post_data)

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == f"400 {message}"

    @pytest.mark.parametrize("name", ["requirements.txt", "rrequirements.txt"])
    def test_fails_with_invalid_names(self, pyramid_config, db_request, name):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": name,
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
                "content": pretend.stub(
                    filename=f"{name}-1.0.tar.gz",
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="project-name")]

        assert resp.status_code == 400
        assert resp.status == (
            "400 The name {!r} isn't allowed. "
            "See /the/help/url/ "
            "for more information."
        ).format(name)

    @pytest.mark.parametrize(
        "conflicting_name",
        [
            "toast1ng",
            "toastlng",
            "t0asting",
            "toast-ing",
            "toast.ing",
            "toast_ing",
        ],
    )
    def test_fails_with_ultranormalized_names(
        self, pyramid_config, db_request, conflicting_name
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        ProjectFactory.create(name="toasting")
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.db.flush()

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": conflicting_name,
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
                "content": pretend.stub(
                    filename=f"{conflicting_name}-1.0.tar.gz",
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="project-name")]

        assert resp.status_code == 400
        assert resp.status == (
            "400 The name {!r} is too similar to an existing project. "
            "See /the/help/url/ for more information."
        ).format(conflicting_name)

    @pytest.mark.parametrize(
        ("description_content_type", "description", "message"),
        [
            (
                "text/x-rst",
                ".. invalid-directive::",
                "400 The description failed to render for 'text/x-rst'. "
                "See /the/help/url/ for more information.",
            ),
            (
                "",
                ".. invalid-directive::",
                "400 The description failed to render in the default format "
                "of reStructuredText. "
                "See /the/help/url/ for more information.",
            ),
        ],
    )
    def test_fails_invalid_render(
        self, pyramid_config, db_request, description_content_type, description, message
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
                "content": pretend.stub(
                    filename="example-1.0.tar.gz",
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
                "description_content_type": description_content_type,
                "description": description,
            }
        )

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [
            pretend.call(_anchor="description-content-type")
        ]

        assert resp.status_code == 400
        assert resp.status == message

    @pytest.mark.parametrize(
        "name",
        [
            "xml",
            "XML",
            "pickle",
            "PiCKle",
            "main",
            "future",
            "al",
            "uU",
            "test",
            "encodings.utf_8_sig",
            "distutils.command.build_clib",
            "xmlrpc",
            "xmlrpc.server",
            "xml.etree",
            "xml.etree.ElementTree",
            "xml.parsers",
            "xml.parsers.expat",
            "xml.parsers.expat.errors",
            "encodings.idna",
            "encodings",
            "CGIHTTPServer",
            "cgihttpserver",
        ],
    )
    def test_fails_with_stdlib_names(self, pyramid_config, db_request, name):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": name,
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
                "content": pretend.stub(
                    filename=f"{name}-1.0.tar.gz",
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="project-name")]

        assert resp.status_code == 400
        assert resp.status == (
            "400 The name {!r} isn't allowed (conflict "
            "with Python Standard Library module name). "
            "See /the/help/url/ "
            "for more information."
        ).format(name)

    def test_fails_with_admin_flag_set(self, pyramid_config, db_request):
        admin_flag = (
            db_request.db.query(AdminFlag)
            .filter(
                AdminFlag.id == AdminFlagValue.DISALLOW_NEW_PROJECT_REGISTRATION.value
            )
            .first()
        )
        admin_flag.enabled = True
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        name = "fails-with-admin-flag"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": name,
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
                "content": pretend.stub(
                    filename=f"{name}-1.0.tar.gz",
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPForbidden) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == (
            "403 New project registration temporarily "
            "disabled. See "
            "/the/help/url/ for "
            "more information."
        )

    def test_upload_fails_without_file(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Upload payload does not have a file."

    @pytest.mark.parametrize("value", [("UNKNOWN"), ("UNKNOWN\n\n")])
    def test_upload_cleans_unknown_values(self, pyramid_config, db_request, value):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": value,
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
            }
        )

        with pytest.raises(HTTPBadRequest):
            legacy.file_upload(db_request)

        assert "name" not in db_request.POST

    def test_upload_escapes_nul_characters(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "testing",
                "summary": "I want to go to the \x00",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": "a fake md5 digest",
            }
        )

        with pytest.raises(HTTPBadRequest):
            legacy.file_upload(db_request)

        assert "\x00" not in db_request.POST["summary"]

    @pytest.mark.parametrize(
        ("digests",),
        [
            ({"md5_digest": _TAR_GZ_PKG_MD5},),
            ({"sha256_digest": _TAR_GZ_PKG_SHA256},),
            ({"md5_digest": _TAR_GZ_PKG_MD5},),
            ({"sha256_digest": _TAR_GZ_PKG_SHA256},),
            (
                {
                    "md5_digest": _TAR_GZ_PKG_MD5,
                    "sha256_digest": _TAR_GZ_PKG_SHA256,
                },
            ),
            (
                {
                    "md5_digest": _TAR_GZ_PKG_MD5,
                    "sha256_digest": _TAR_GZ_PKG_SHA256,
                },
            ),
        ],
    )
    def test_successful_upload(
        self,
        tmpdir,
        monkeypatch,
        pyramid_config,
        db_request,
        digests,
        metrics,
    ):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        db_request.db.add(Classifier(classifier="Environment :: Other Environment"))

        filename = f"{project.name}-{release.version}.tar.gz"

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"

        content = FieldStorage()
        content.filename = filename
        content.file = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        content.type = "application/tar"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "pyversion": "source",
                "content": content,
                "description": "an example description",
            }
        )
        db_request.POST.extend([("classifiers", "Environment :: Other Environment")])
        db_request.POST.update(digests)

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            expected = _TAR_GZ_PKG_TESTDATA
            with open(file_path, "rb") as fp:
                assert fp.read() == expected

        storage_service = pretend.stub(store=storage_service_store)
        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                IFileStorage: storage_service,
                IMetricsService: metrics,
            }.get(svc)
        )
        db_request.registry.settings = {
            "warehouse.release_files_table": "example.pypi.distributions"
        }

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200
        assert db_request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IFileStorage, name="archive"),
        ]
        assert len(storage_service.store.calls) == 1
        assert storage_service.store.calls[0] == pretend.call(
            "/".join(
                [
                    _TAR_GZ_PKG_STORAGE_HASH[:2],
                    _TAR_GZ_PKG_STORAGE_HASH[2:4],
                    _TAR_GZ_PKG_STORAGE_HASH[4:],
                    filename,
                ]
            ),
            mock.ANY,
            meta={
                "project": project.normalized_name,
                "version": release.version,
                "package-type": "sdist",
                "python-version": "source",
            },
        )

        # Ensure that a File object has been created.
        uploaded_file = (
            db_request.db.query(File)
            .filter((File.release == release) & (File.filename == filename))
            .one()
        )

        assert uploaded_file.uploaded_via == "warehouse-tests/6.6.6"

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename).filter(Filename.filename == filename).one()

        # Ensure that all of our journal entries have been created
        journals = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [(j.name, j.version, j.action, j.submitted_by) for j in journals] == [
            (
                release.project.name,
                release.version,
                f"add source file {filename}",
                user,
            )
        ]

        assert db_request.task.calls == [
            pretend.call(update_bigquery_release_files),
            pretend.call(sync_file_to_cache),
        ]

        assert metrics.increment.calls == [
            pretend.call("warehouse.upload.attempt"),
            pretend.call("warehouse.upload.ok", tags=["filetype:sdist"]),
        ]

    @pytest.mark.parametrize("content_type", [None, "image/foobar"])
    def test_upload_fails_invalid_content_type(
        self, tmpdir, monkeypatch, pyramid_config, db_request, content_type
    ):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        db_request.db.add(Classifier(classifier="Environment :: Other Environment"))

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "pyversion": "source",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type=content_type,
                ),
            }
        )
        db_request.POST.extend([("classifiers", "Environment :: Other Environment")])

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Invalid distribution file."

    def test_upload_fails_with_legacy_type(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "bdist_dumb",
                "pyversion": "2.7",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert (
            resp.status
            == "400 Invalid value for filetype. Error: Use a known file type."
        )

    def test_upload_fails_with_legacy_ext(self, pyramid_config, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.bz2"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": _TAR_BZ2_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_BZ2_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 Invalid file extension: Use .tar.gz, .whl or .zip "
            "extension. See https://www.python.org/dev/peps/pep-0527 "
            "and https://peps.python.org/pep-0715/ for more information"
        )

    def test_upload_fails_for_second_sdist(self, pyramid_config, db_request):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        FileFactory.create(
            release=release,
            packagetype="sdist",
            filename=f"{project.name}-{release.version}.tar.gz",
        )
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.zip"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"A fake file."),
                    type="application/zip",
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Only one sdist may be uploaded per release."

    def test_upload_fails_with_invalid_classifier(self, pyramid_config, db_request):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )
        db_request.POST.extend([("classifiers", "Invalid :: Classifier")])

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 Invalid value for classifiers. Error: Classifier 'Invalid :: "
            "Classifier' is not a valid classifier."
        )

    @pytest.mark.parametrize(
        "deprecated_classifiers, expected",
        [
            (
                {"AA :: BB": ["CC :: DD"]},
                "400 Invalid value for classifiers. Error: Classifier 'AA :: "
                "BB' has been deprecated, use the following classifier(s) "
                "instead: ['CC :: DD']",
            ),
            (
                {"AA :: BB": []},
                "400 Invalid value for classifiers. Error: Classifier 'AA :: "
                "BB' has been deprecated.",
            ),
        ],
    )
    def test_upload_fails_with_deprecated_classifier(
        self, pyramid_config, db_request, monkeypatch, deprecated_classifiers, expected
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)
        classifier = ClassifierFactory(classifier="AA :: BB")

        monkeypatch.setattr(legacy, "deprecated_classifiers", deprecated_classifiers)

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )
        db_request.POST.extend([("classifiers", classifier.classifier)])
        db_request.route_url = pretend.call_recorder(lambda *a, **kw: "/url")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == expected

    @pytest.mark.parametrize(
        "digests",
        [
            {"md5_digest": "bad"},
            {
                "sha256_digest": (
                    "badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbad"
                    "badbadb"
                )
            },
            {
                "md5_digest": "bad",
                "sha256_digest": (
                    "badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbad"
                    "badbadb"
                ),
            },
            {
                "md5_digest": _TAR_GZ_PKG_MD5,
                "sha256_digest": (
                    "badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbad"
                    "badbadb"
                ),
            },
            {
                "md5_digest": "bad",
                "sha256_digest": (
                    "4a8422abcc484a4086bdaa618c65289f749433b07eb433c51c4e37714"
                    "3ff5fdb"
                ),
            },
        ],
    )
    def test_upload_fails_with_invalid_digest(
        self, pyramid_config, db_request, digests
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )
        db_request.POST.update(digests)

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 The digest supplied does not match a digest calculated "
            "from the uploaded file."
        )

    def test_upload_fails_with_invalid_file(self, pyramid_config, db_request):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.zip"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "0cc175b9c0f1b6a831c399e269772661",
                "content": pretend.stub(
                    filename=filename, file=io.BytesIO(b"a"), type="application/zip"
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Invalid distribution file."

    def test_upload_fails_end_of_file_error(
        self, pyramid_config, db_request, metrics, project_service
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name="Package-Name")
        RoleFactory.create(user=user, project=project)

        # Malformed tar.gz, triggers EOF error
        file_contents = b"\x8b\x08\x00\x00\x00\x00\x00\x00\xff"

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.1",
                "name": "malformed",
                "version": "1.1",
                "summary": "This is my summary!",
                "filetype": "sdist",
                "md5_digest": hashlib.md5(file_contents).hexdigest(),
                "content": pretend.stub(
                    filename="malformed-1.1.tar.gz",
                    file=io.BytesIO(file_contents),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Invalid distribution file."

    def test_upload_fails_with_too_large_file(self, pyramid_config, db_request):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name="foobar", upload_limit=(100 * 1024 * 1024))
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (project.upload_limit + 1)),
                    type="application/tar",
                ),
            }
        )
        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="file-size-limit")]
        assert resp.status_code == 400
        assert resp.status == (
            "400 File too large. Limit for project 'foobar' is 100 MB. "
            "See /the/help/url/ for more information."
        )

    def test_upload_fails_with_too_large_project_size_default_limit(
        self, pyramid_config, db_request
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create(
            name="foobar",
            upload_limit=legacy.MAX_FILESIZE,
            total_size=legacy.MAX_PROJECT_SIZE - 1,
        )
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * 2),
                    type="application/tar",
                ),
            }
        )
        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="project-size-limit")]
        assert resp.status_code == 400
        assert resp.status == (
            "400 Project size too large."
            + " Limit for project 'foobar' total size is 10 GB. "
            "See /the/help/url/"
        )

    def test_upload_fails_with_too_large_project_size_custom_limit(
        self, pyramid_config, db_request
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        one_megabyte = 1 * 1024 * 1024
        project = ProjectFactory.create(
            name="foobar",
            upload_limit=legacy.MAX_FILESIZE,
            total_size=legacy.MAX_PROJECT_SIZE,
            total_size_limit=legacy.MAX_PROJECT_SIZE
            + one_megabyte,  # Custom Limit for the project
        )
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (one_megabyte + 1)),
                    type="application/tar",
                ),
            }
        )
        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="project-size-limit")]
        assert resp.status_code == 400
        assert resp.status == (
            "400 Project size too large."
            + " Limit for project 'foobar' total size is 10 GB. "
            "See /the/help/url/"
        )

    def test_upload_succeeds_custom_project_size_limit(
        self,
        pyramid_config,
        db_request,
        metrics,
        project_service,
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        one_megabyte = 1 * 1024 * 1024
        project = ProjectFactory.create(
            name="foobar",
            upload_limit=legacy.MAX_FILESIZE,
            total_size=legacy.MAX_PROJECT_SIZE,
            total_size_limit=legacy.MAX_PROJECT_SIZE
            + (one_megabyte * 60),  # Custom Limit for the project
        )
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format("example", "1.0")

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Project object has been created.
        project = db_request.db.query(Project).filter(Project.name == "example").one()

        # Ensure that a Role with the user as owner has been created.
        role = (
            db_request.db.query(Role)
            .filter((Role.user == user) & (Role.project == project))
            .one()
        )
        assert role.role_name == "Owner"

        # Ensure that a Release object has been created.
        release = (
            db_request.db.query(Release)
            .filter((Release.project == project) & (Release.version == "1.0"))
            .one()
        )

        assert release.uploaded_via == "warehouse-tests/6.6.6"

        # Ensure that a File object has been created.
        db_request.db.query(File).filter(
            (File.release == release) & (File.filename == filename)
        ).one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename).filter(Filename.filename == filename).one()

        # Ensure that all of our journal entries have been created
        journals = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [(j.name, j.version, j.action, j.submitted_by) for j in journals] == [
            ("example", None, "create", user),
            ("example", None, f"add Owner {user.username}", user),
            ("example", "1.0", "new release", user),
            ("example", "1.0", "add source file example-1.0.tar.gz", user),
        ]

    def test_upload_fails_with_previously_used_filename(
        self, pyramid_config, db_request
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": hashlib.md5(file_content.getvalue()).hexdigest(),
                "content": pretend.stub(
                    filename=filename, file=file_content, type="application/tar"
                ),
            }
        )

        db_request.db.add(Filename(filename=filename))
        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="file-name-reuse")]
        assert resp.status_code == 400
        assert resp.status == (
            "400 This filename has already been used, use a "
            "different version. "
            "See /the/help/url/ for more information."
        )

    def test_upload_noop_with_existing_filename_same_content(
        self, pyramid_config, db_request
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.tm = pretend.stub(doom=pretend.call_recorder(lambda: None))
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": hashlib.md5(file_content.getvalue()).hexdigest(),
                "content": pretend.stub(
                    filename=filename, file=file_content, type="application/tar"
                ),
            }
        )

        db_request.db.add(
            FileFactory.create(
                release=release,
                filename=filename,
                md5_digest=hashlib.md5(file_content.getvalue()).hexdigest(),
                sha256_digest=hashlib.sha256(file_content.getvalue()).hexdigest(),
                blake2_256_digest=hashlib.blake2b(
                    file_content.getvalue(), digest_size=256 // 8
                ).hexdigest(),
                path="source/{name[0]}/{name}/{filename}".format(
                    name=project.name, filename=filename
                ),
            )
        )

        resp = legacy.file_upload(db_request)

        assert db_request.tm.doom.calls == [pretend.call()]
        assert resp.status_code == 200

    def test_upload_fails_with_existing_filename_diff_content(
        self, pyramid_config, db_request
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": hashlib.md5(file_content.getvalue()).hexdigest(),
                "content": pretend.stub(
                    filename=filename, file=file_content, type="application/tar"
                ),
            }
        )

        db_request.db.add(
            FileFactory.create(
                release=release,
                filename=filename,
                md5_digest=hashlib.md5(filename.encode("utf8")).hexdigest(),
                sha256_digest=hashlib.sha256(filename.encode("utf8")).hexdigest(),
                blake2_256_digest=hashlib.blake2b(
                    filename.encode("utf8"), digest_size=256 // 8
                ).hexdigest(),
                path="source/{name[0]}/{name}/{filename}".format(
                    name=project.name, filename=filename
                ),
            )
        )
        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")
        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="file-name-reuse")]
        assert resp.status_code == 400
        assert resp.status == (
            "400 File already exists. See /the/help/url/ for more information."
        )

    def test_upload_fails_with_diff_filename_same_blake2(
        self, pyramid_config, db_request
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.gz"
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": hashlib.md5(file_content.getvalue()).hexdigest(),
                "content": pretend.stub(
                    filename=f"{project.name}-fake.tar.gz",
                    file=file_content,
                    type="application/tar",
                ),
            }
        )

        db_request.db.add(
            FileFactory.create(
                release=release,
                filename=filename,
                md5_digest=hashlib.md5(file_content.getvalue()).hexdigest(),
                sha256_digest=hashlib.sha256(file_content.getvalue()).hexdigest(),
                blake2_256_digest=hashlib.blake2b(
                    file_content.getvalue(), digest_size=256 // 8
                ).hexdigest(),
                path="source/{name[0]}/{name}/{filename}".format(
                    name=project.name, filename=filename
                ),
            )
        )
        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="file-name-reuse")]
        assert resp.status_code == 400
        assert resp.status == (
            "400 File already exists. See /the/help/url/ for more information."
        )

    @pytest.mark.parametrize(
        "filename, filetype, project_name",
        [
            # completely different
            ("nope-{version}.tar.gz", "sdist", "something_else"),
            ("nope-{version}-py3-none-any.whl", "bdist_wheel", "something_else"),
            # starts with same prefix
            ("nope-{version}.tar.gz", "sdist", "no"),
            ("nope-{version}-py3-none-any.whl", "bdist_wheel", "no"),
            # starts with same prefix with hyphen
            ("no-way-{version}.tar.gz", "sdist", "no"),
            ("no_way-{version}-py3-none-any.whl", "bdist_wheel", "no"),
            # multiple delimiters
            ("foo__bar-{version}-py3-none-any.whl", "bdist_wheel", "foo-.bar"),
        ],
    )
    def test_upload_fails_with_wrong_filename(
        self, pyramid_config, db_request, metrics, filename, filetype, project_name
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name=project_name)
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
        }.get(svc)

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": filetype,
                "md5_digest": _TAR_GZ_PKG_MD5,
                "pyversion": {
                    "bdist_wheel": "1.0",
                    "bdist_egg": "1.0",
                    "sdist": "source",
                }[filetype],
                "content": pretend.stub(
                    filename=filename.format(version=release.version),
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )
        db_request.help_url = lambda **kw: "/the/help/url/"

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 Start filename for {!r} with {!r}.".format(
                project.name,
                project.normalized_name.replace("-", "_"),
            )
        )

    @pytest.mark.parametrize(
        "filetype, extension",
        [
            ("sdist", ".whl"),
            ("bdist_wheel", ".tar.gz"),
            ("bdist_wheel", ".zip"),
        ],
    )
    def test_upload_fails_with_invalid_filetype(
        self, pyramid_config, db_request, filetype, extension
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}{extension}"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": filetype,
                "md5_digest": "nope!",
                "pyversion": {
                    "bdist_wheel": "1.0",
                    "bdist_egg": "1.0",
                    "sdist": "source",
                }[filetype],
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (legacy.MAX_FILESIZE + 1)),
                    type="application/tar",
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            f"400 Invalid file extension: Extension {extension} is invalid for "
            f"filetype {filetype}. See https://www.python.org/dev/peps/pep-0527 "
            "for more information."
        )

    def test_upload_fails_with_invalid_extension(self, pyramid_config, db_request):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}.tar.wat"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (legacy.MAX_FILESIZE + 1)),
                    type="application/tar",
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 Invalid file extension: Use .tar.gz, .whl or .zip "
            "extension. See https://www.python.org/dev/peps/pep-0527 "
            "and https://peps.python.org/pep-0715/ for more information"
        )

    @pytest.mark.parametrize("character", ["/", "\\"])
    def test_upload_fails_with_unsafe_filename(
        self, pyramid_config, db_request, character
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{character + project.name}-{release.version}.tar.wat"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (legacy.MAX_FILESIZE + 1)),
                    type="application/tar",
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Cannot upload a file with '/' or '\\' in the name."

    @pytest.mark.parametrize("character", [*(chr(x) for x in range(32)), chr(127)])
    def test_upload_fails_with_disallowed_in_filename(
        self, pyramid_config, db_request, character
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}{character}-{release.version}.tar.wat"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (legacy.MAX_FILESIZE + 1)),
                    type="application/tar",
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 Cannot upload a file with non-printable characters (ordinals 0-31) "
            "or the DEL character (ordinal 127) in the name."
        )

    def test_upload_fails_without_user_permission(self, pyramid_config, db_request):
        user1 = UserFactory.create()
        EmailFactory.create(user=user1)
        user2 = UserFactory.create()
        EmailFactory.create(user=user2)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user1, project=project)

        filename = f"{project.name}-{release.version}.tar.wat"

        pyramid_config.testing_securitypolicy(identity=user2, permissive=False)
        db_request.user = user2
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (legacy.MAX_FILESIZE + 1)),
                    type="application/tar",
                ),
            }
        )

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPForbidden) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="project-name")]
        assert resp.status_code == 403
        assert resp.status == (
            "403 The user '{}' "
            "isn't allowed to upload to project '{}'. "
            "See /the/help/url/ for more information."
        ).format(user2.username, project.name)

    def test_upload_fails_without_oidc_publisher_permission(
        self, pyramid_config, db_request
    ):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")

        publisher = GitHubPublisherFactory.create(projects=[project])

        filename = f"{project.name}-{release.version}.tar.wat"

        pyramid_config.testing_securitypolicy(identity=publisher, permissive=False)
        db_request.user = None
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": "nope!",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"a" * (legacy.MAX_FILESIZE + 1)),
                    type="application/tar",
                ),
            }
        )

        db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPForbidden) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert db_request.help_url.calls == [pretend.call(_anchor="project-name")]
        assert resp.status_code == 403
        assert resp.status == (
            "403 The given token isn't allowed to upload to project '{}'. "
            "See /the/help/url/ for more information."
        ).format(project.name)

    def test_basic_auth_upload_fails_with_2fa_enabled(
        self, pyramid_config, db_request, metrics, monkeypatch
    ):
        user = UserFactory.create(totp_secret=b"secret")
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": "1.0.0",
                "summary": "This is my summary!",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename="{}-{}.tar.gz".format(project.name, "1.0.0"),
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )
        db_request.authentication_method = AuthenticationMethod.BASIC_AUTH

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(legacy, "send_basic_auth_with_two_factor_email", send_email)

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
        }.get(svc)

        with pytest.raises(BasicAuthTwoFactorEnabled) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 401
        assert resp.status == (
            f"401 User { user.username } has two factor auth enabled, "
            "an API Token or Trusted Publisher must be used to upload "
            "in place of password."
        )
        assert send_email.calls == [
            pretend.call(db_request, user, project_name=project.name)
        ]

    @pytest.mark.parametrize(
        "plat",
        [
            "any",
            "win32",
            "win_amd64",
            "win_ia64",
            "manylinux1_i686",
            "manylinux1_x86_64",
            "manylinux2010_i686",
            "manylinux2010_x86_64",
            "manylinux2014_i686",
            "manylinux2014_x86_64",
            "manylinux2014_aarch64",
            "manylinux2014_armv7l",
            "manylinux2014_ppc64",
            "manylinux2014_ppc64le",
            "manylinux2014_s390x",
            "manylinux_2_5_i686",
            "manylinux_2_12_x86_64",
            "manylinux_2_17_aarch64",
            "manylinux_2_17_armv7l",
            "manylinux_2_17_ppc64",
            "manylinux_2_17_ppc64le",
            "manylinux_3_0_s390x",
            "musllinux_1_1_x86_64",
            "macosx_10_6_intel",
            "macosx_10_13_x86_64",
            "macosx_11_0_x86_64",
            "macosx_10_15_arm64",
            "macosx_11_10_universal2",
            # A real tag used by e.g. some numpy wheels
            (
                "macosx_10_6_intel.macosx_10_9_intel.macosx_10_9_x86_64."
                "macosx_10_10_intel.macosx_10_10_x86_64"
            ),
        ],
    )
    def test_upload_succeeds_with_wheel(
        self, tmpdir, monkeypatch, pyramid_config, db_request, plat, metrics
    ):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}-cp34-none-{plat}.whl"
        filebody = _get_whl_testdata(name=project.name, version=release.version)
        filestoragehash = _storage_hash(filebody)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "bdist_wheel",
                "pyversion": "cp34",
                "md5_digest": hashlib.md5(filebody).hexdigest(),
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(filebody),
                    type="application/zip",
                ),
            }
        )

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            with open(file_path, "rb") as fp:
                if file_path.endswith(".metadata"):
                    assert fp.read() == b"Fake metadata"
                else:
                    assert fp.read() == filebody

        storage_service = pretend.stub(store=storage_service_store)

        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                IFileStorage: storage_service,
                IMetricsService: metrics,
            }.get(svc)
        )

        monkeypatch.setattr(legacy, "_is_valid_dist_file", lambda *a, **kw: True)

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200
        assert db_request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IFileStorage, name="archive"),
        ]
        assert storage_service.store.calls == [
            pretend.call(
                "/".join(
                    [
                        filestoragehash[:2],
                        filestoragehash[2:4],
                        filestoragehash[4:],
                        filename,
                    ]
                ),
                mock.ANY,
                meta={
                    "project": project.normalized_name,
                    "version": release.version,
                    "package-type": "bdist_wheel",
                    "python-version": "cp34",
                },
            ),
            pretend.call(
                "/".join(
                    [
                        filestoragehash[:2],
                        filestoragehash[2:4],
                        filestoragehash[4:],
                        filename + ".metadata",
                    ]
                ),
                mock.ANY,
                meta={
                    "project": project.normalized_name,
                    "version": release.version,
                    "package-type": "bdist_wheel",
                    "python-version": "cp34",
                },
            ),
        ]

        # Ensure that a File object has been created.
        db_request.db.query(File).filter(
            (File.release == release) & (File.filename == filename)
        ).one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename).filter(Filename.filename == filename).one()

        # Ensure that all of our journal entries have been created
        journals = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [(j.name, j.version, j.action, j.submitted_by) for j in journals] == [
            (
                release.project.name,
                release.version,
                f"add cp34 file {filename}",
                user,
            )
        ]

        assert metrics.increment.calls == [
            pretend.call("warehouse.upload.attempt"),
            pretend.call("warehouse.upload.ok", tags=["filetype:bdist_wheel"]),
        ]

    @pytest.mark.parametrize(
        "project_name, version",
        [
            ("foo", "1.0.0"),
            ("foo-bar", "1.0.0"),
            ("typesense-server-wrapper-chunk1", "1"),
        ],
    )
    def test_upload_succeeds_metadata_check(
        self,
        monkeypatch,
        db_request,
        pyramid_config,
        metrics,
        project_name,
        version,
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name=project_name)
        RoleFactory.create(user=user, project=project)

        filename = (
            f"{project.normalized_name.replace('-', '_')}-{version}-py3-none-any.whl"
        )
        filebody = _get_whl_testdata(
            name=project.normalized_name.replace("-", "_"), version=version
        )

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            with open(file_path, "rb") as fp:
                if file_path.endswith(".metadata"):
                    assert fp.read() == b"Fake metadata"
                else:
                    assert fp.read() == filebody

        storage_service = pretend.stub(store=storage_service_store)

        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                IFileStorage: storage_service,
                IMetricsService: metrics,
            }.get(svc)
        )

        monkeypatch.setattr(legacy, "_is_valid_dist_file", lambda *a, **kw: True)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": "1.0.0",
                "filetype": "bdist_wheel",
                "pyversion": "py3",
                "md5_digest": hashlib.md5(filebody).hexdigest(),
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(filebody),
                    type="application/zip",
                ),
            }
        )

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "project_name, filename_prefix",
        [
            ("flufl.enum", "flufl_enum"),
            ("foo-.bar", "foo_bar"),
        ],
    )
    def test_upload_succeeds_pep427_normalized_filename(
        self,
        monkeypatch,
        db_request,
        pyramid_config,
        metrics,
        project_name,
        filename_prefix,
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name=project_name)
        RoleFactory.create(user=user, project=project)

        filename = f"{filename_prefix}-1.0.0-py3-none-any.whl"
        filebody = _get_whl_testdata(name=filename_prefix, version="1.0.0")

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            with open(file_path, "rb") as fp:
                if file_path.endswith(".metadata"):
                    assert fp.read() == b"Fake metadata"
                else:
                    assert fp.read() == filebody

        storage_service = pretend.stub(store=storage_service_store)

        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                IFileStorage: storage_service,
                IMetricsService: metrics,
            }.get(svc)
        )

        monkeypatch.setattr(legacy, "_is_valid_dist_file", lambda *a, **kw: True)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": "1.0.0",
                "filetype": "bdist_wheel",
                "pyversion": "py3",
                "md5_digest": hashlib.md5(filebody).hexdigest(),
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(filebody),
                    type="application/zip",
                ),
            }
        )

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a File object has been created.
        db_request.db.query(File).filter(File.filename == filename).one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename).filter(Filename.filename == filename).one()

    def test_upload_succeeds_with_wheel_after_sdist(
        self, tmpdir, monkeypatch, pyramid_config, db_request, metrics
    ):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        FileFactory.create(
            release=release,
            packagetype="sdist",
            filename=f"{project.name}-{release.version}.tar.gz",
        )
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}-cp34-none-any.whl"
        filebody = _get_whl_testdata(name=project.name, version=release.version)
        filestoragehash = _storage_hash(filebody)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "bdist_wheel",
                "pyversion": "cp34",
                "md5_digest": hashlib.md5(filebody).hexdigest(),
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(filebody),
                    type="application/zip",
                ),
            }
        )

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            with open(file_path, "rb") as fp:
                if file_path.endswith(".metadata"):
                    assert fp.read() == b"Fake metadata"
                else:
                    assert fp.read() == filebody

        storage_service = pretend.stub(store=storage_service_store)
        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                IFileStorage: storage_service,
                IMetricsService: metrics,
            }.get(svc)
        )

        monkeypatch.setattr(legacy, "_is_valid_dist_file", lambda *a, **kw: True)

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200
        assert db_request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IFileStorage, name="archive"),
        ]
        assert storage_service.store.calls == [
            pretend.call(
                "/".join(
                    [
                        filestoragehash[:2],
                        filestoragehash[2:4],
                        filestoragehash[4:],
                        filename,
                    ]
                ),
                mock.ANY,
                meta={
                    "project": project.normalized_name,
                    "version": release.version,
                    "package-type": "bdist_wheel",
                    "python-version": "cp34",
                },
            ),
            pretend.call(
                "/".join(
                    [
                        filestoragehash[:2],
                        filestoragehash[2:4],
                        filestoragehash[4:],
                        filename + ".metadata",
                    ]
                ),
                mock.ANY,
                meta={
                    "project": project.normalized_name,
                    "version": release.version,
                    "package-type": "bdist_wheel",
                    "python-version": "cp34",
                },
            ),
        ]

        # Ensure that a File object has been created.
        db_request.db.query(File).filter(
            (File.release == release) & (File.filename == filename)
        ).one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename).filter(Filename.filename == filename).one()

        # Ensure that all of our journal entries have been created
        journals = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [(j.name, j.version, j.action, j.submitted_by) for j in journals] == [
            (
                release.project.name,
                release.version,
                f"add cp34 file {filename}",
                user,
            )
        ]

    @pytest.mark.parametrize(
        "filename, expected",
        [
            (
                "foo-1.0.whl",
                "400 Invalid wheel filename (wrong number of parts): foo-1.0",
            ),
            (
                "foo-1.0-q-py3-none-any.whl",
                "400 Invalid build number: q in 'foo-1.0-q-py3-none-any'",
            ),
            (
                "foo-0.0.4test1-py3-none-any.whl",
                "400 Invalid wheel filename (invalid version): "
                "foo-0.0.4test1-py3-none-any",
            ),
        ],
    )
    def test_upload_fails_with_invalid_filename(
        self, monkeypatch, pyramid_config, db_request, filename, expected
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name="foo")
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filebody = _get_whl_testdata(name=project.name, version=release.version)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "bdist_wheel",
                "pyversion": "cp34",
                "md5_digest": hashlib.md5(filebody).hexdigest(),
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(filebody),
                    type="application/zip",
                ),
            }
        )

        monkeypatch.setattr(legacy, "_is_valid_dist_file", lambda *a, **kw: True)

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == expected

    @pytest.mark.parametrize(
        "plat",
        [
            "linux_x86_64",
            "linux_x86_64.win32",
            "macosx_9_2_x86_64",
            "macosx_15_2_arm64",
            "macosx_10_15_amd64",
        ],
    )
    def test_upload_fails_with_unsupported_wheel_plat(
        self, monkeypatch, pyramid_config, db_request, plat
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = f"{project.name}-{release.version}-cp34-none-{plat}.whl"

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "bdist_wheel",
                "pyversion": "cp34",
                "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(b"A fake file."),
                    type="application/tar",
                ),
            }
        )

        monkeypatch.setattr(legacy, "_is_valid_dist_file", lambda *a, **kw: True)

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert re.match(
            "400 Binary wheel .* has an unsupported platform tag .*", resp.status
        )

    def test_upload_fails_with_missing_metadata_wheel(
        self, monkeypatch, pyramid_config, db_request
    ):
        user = UserFactory.create()
        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        temp_f = io.BytesIO()
        with zipfile.ZipFile(file=temp_f, mode="w") as zfp:
            zfp.writestr("some_file", "some_data")

        filename = f"{project.name}-{release.version}-cp34-none-any.whl"
        filebody = temp_f.getvalue()

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "bdist_wheel",
                "pyversion": "cp34",
                "md5_digest": hashlib.md5(filebody).hexdigest(),
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(filebody),
                    type="application/zip",
                ),
            }
        )

        monkeypatch.setattr(legacy, "_is_valid_dist_file", lambda *a, **kw: True)

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert re.match(
            "400 Wheel .* does not contain the required METADATA file: .*", resp.status
        )

    def test_upload_updates_existing_project_name(
        self, pyramid_config, db_request, metrics
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name="Package-Name")
        RoleFactory.create(user=user, project=project)

        new_project_name = "package-name"
        filename = "{}-{}.tar.gz".format(new_project_name, "1.1")

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.1",
                "name": new_project_name,
                "version": "1.1",
                "summary": "This is my summary!",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Project object name has been updated.
        project = (
            db_request.db.query(Project).filter(Project.name == new_project_name).one()
        )

        # Ensure that a Release object has been created.
        release = (
            db_request.db.query(Release)
            .filter((Release.project == project) & (Release.version == "1.1"))
            .one()
        )

        assert release.uploaded_via == "warehouse-tests/6.6.6"

    @pytest.mark.parametrize(
        "version, expected_version",
        [
            ("1.0", "1.0"),
            ("v1.0", "1.0"),
        ],
    )
    @pytest.mark.parametrize(
        "test_with_user",
        [
            True,
            False,
        ],
    )
    def test_upload_succeeds_creates_release(
        self,
        monkeypatch,
        pyramid_config,
        db_request,
        metrics,
        version,
        expected_version,
        test_with_user,
    ):
        from warehouse.events.models import HasEvents
        from warehouse.events.tags import EventTag

        project = ProjectFactory.create()
        if test_with_user:
            identity = UserFactory.create()
            EmailFactory.create(user=identity)
            RoleFactory.create(user=identity, project=project)
        else:
            publisher = GitHubPublisherFactory.create(projects=[project])
            claims = {"sha": "somesha"}
            identity = OIDCContext(publisher, SignedClaims(claims))
            db_request.oidc_publisher = identity.publisher
            db_request.oidc_claims = identity.claims

        db_request.db.add(Classifier(classifier="Environment :: Other Environment"))
        db_request.db.add(Classifier(classifier="Programming Language :: Python"))

        filename = "{}-{}.tar.gz".format(project.name, "1.0")

        pyramid_config.testing_securitypolicy(identity=identity)
        db_request.user = identity if test_with_user else None
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": version,
                "summary": "This is my summary!",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )
        db_request.POST.extend(
            [
                ("classifiers", "Environment :: Other Environment"),
                ("classifiers", "Programming Language :: Python"),
                ("requires_dist", "foo"),
                ("requires_dist", "bar (>1.0)"),
                ("project_urls", "Test, https://example.com/"),
                ("requires_external", "Cheese (>1.0)"),
                ("provides", "testing"),
            ]
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
        }.get(svc)

        record_event = pretend.call_recorder(
            lambda self, *, tag, request=None, additional: None
        )
        monkeypatch.setattr(HasEvents, "record_event", record_event)

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Release object has been created.
        release = (
            db_request.db.query(Release)
            .filter(
                (Release.project == project) & (Release.version == expected_version)
            )
            .one()
        )
        assert release.summary == "This is my summary!"
        assert release.classifiers == [
            "Environment :: Other Environment",
            "Programming Language :: Python",
        ]
        assert set(release.requires_dist) == {"foo", "bar (>1.0)"}
        assert release.project_urls == {"Test": "https://example.com/"}
        assert set(release.requires_external) == {"Cheese (>1.0)"}
        assert set(release.provides) == {"testing"}
        assert release.version == expected_version
        assert release.canonical_version == "1"
        assert release.uploaded_via == "warehouse-tests/6.6.6"

        # Ensure that a File object has been created.
        db_request.db.query(File).filter(
            (File.release == release) & (File.filename == filename)
        ).one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename).filter(Filename.filename == filename).one()

        # Ensure that all of our journal entries have been created
        journals = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [(j.name, j.version, j.action, j.submitted_by) for j in journals] == [
            (
                release.project.name,
                release.version,
                "new release",
                identity if test_with_user else None,
            ),
            (
                release.project.name,
                release.version,
                f"add source file {filename}",
                identity if test_with_user else None,
            ),
        ]

        # Ensure that all of our events have been created
        release_event = {
            "submitted_by": identity.username
            if test_with_user
            else "OpenID created token",
            "canonical_version": release.canonical_version,
            "publisher_url": f"{identity.publisher.publisher_url()}/commit/somesha"
            if not test_with_user
            else None,
        }

        fileadd_event = {
            "filename": filename,
            "submitted_by": identity.username
            if test_with_user
            else "OpenID created token",
            "canonical_version": release.canonical_version,
            "publisher_url": f"{identity.publisher.publisher_url()}/commit/somesha"
            if not test_with_user
            else None,
            "project_id": str(project.id),
        }

        assert record_event.calls == [
            pretend.call(
                mock.ANY,
                tag=EventTag.Project.ReleaseAdd,
                request=db_request,
                additional=release_event,
            ),
            pretend.call(
                mock.ANY,
                tag=EventTag.File.FileAdd,
                request=db_request,
                additional=fileadd_event,
            ),
        ]

    def test_all_valid_classifiers_can_be_created(self, db_request):
        for classifier in classifiers:
            db_request.db.add(Classifier(classifier=classifier))
        db_request.db.commit()

    @pytest.mark.parametrize("parent_classifier", ["private", "Private", "PrIvAtE"])
    def test_private_classifiers_cannot_be_created(self, db_request, parent_classifier):
        with pytest.raises(IntegrityError):
            db_request.db.add(Classifier(classifier=f"{parent_classifier} :: Foo"))
            db_request.db.commit()

    def test_equivalent_version_one_release(self, pyramid_config, db_request, metrics):
        """
        Test that if a release with a version like '1.0' exists, that a future
        upload with an equivalent version like '1.0.0' will not make a second
        release
        """

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": "1.0.0",
                "summary": "This is my summary!",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename="{}-{}.tar.gz".format(project.name, "1.0.0"),
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
        }.get(svc)

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Release object has been created.
        releases = db_request.db.query(Release).filter(Release.project == project).all()

        # Asset that only one release has been created
        assert releases == [release]

    def test_equivalent_canonical_versions(self, pyramid_config, db_request, metrics):
        """
        Test that if more than one release with equivalent canonical versions
        exists, we use the one that is an exact match
        """

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release_a = ReleaseFactory.create(project=project, version="1.0")
        release_b = ReleaseFactory.create(project=project, version="1.0.0")
        RoleFactory.create(user=user, project=project)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": "1.0.0",
                "summary": "This is my summary!",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename="{}-{}.tar.gz".format(project.name, "1.0.0"),
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
        }.get(svc)

        legacy.file_upload(db_request)

        assert len(release_a.files.all()) == 0
        assert len(release_b.files.all()) == 1

    def test_upload_fails_nonuser_identity_cannot_create_project(
        self, pyramid_config, db_request, metrics
    ):
        publisher = GitHubPublisherFactory.create()

        filename = "{}-{}.tar.gz".format("example", "1.0")

        pyramid_config.testing_securitypolicy(identity=publisher)
        db_request.user = None
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 Non-user identities cannot create new projects. "
            "This was probably caused by successfully using a pending "
            "publisher but specifying the project name incorrectly (either "
            "in the publisher or in your project's metadata). Please ensure "
            "that both match. "
            "See: https://docs.pypi.org/trusted-publishers/troubleshooting/"
        )

    @pytest.mark.parametrize(
        "failing_limiter,remote_addr",
        [
            ("project.create.ip", "127.0.0.1"),
            ("project.create.user", "127.0.0.1"),
            ("project.create.user", None),
        ],
    )
    def test_upload_new_project_fails_ratelimited(
        self,
        pyramid_config,
        db_request,
        metrics,
        project_service,
        failing_limiter,
        remote_addr,
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)

        filename = "{}-{}.tar.gz".format("example", "1.0")

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )
        db_request.remote_addr = remote_addr

        project_service.ratelimiters[failing_limiter] = pretend.stub(
            test=lambda *a, **kw: False,
            resets_in=lambda *a, **kw: 60,
        )
        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        with pytest.raises(HTTPTooManyRequests) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 429
        assert resp.status == ("429 Too many new projects created")

    def test_upload_succeeds_creates_project(
        self, pyramid_config, db_request, metrics, project_service
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)

        filename = "{}-{}.tar.gz".format("example", "1.0")

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Project object has been created.
        project = db_request.db.query(Project).filter(Project.name == "example").one()

        # Ensure that a Role with the user as owner has been created.
        role = (
            db_request.db.query(Role)
            .filter((Role.user == user) & (Role.project == project))
            .one()
        )
        assert role.role_name == "Owner"

        # Ensure that a Release object has been created.
        release = (
            db_request.db.query(Release)
            .filter((Release.project == project) & (Release.version == "1.0"))
            .one()
        )

        assert release.uploaded_via == "warehouse-tests/6.6.6"

        # Ensure that a File object has been created.
        db_request.db.query(File).filter(
            (File.release == release) & (File.filename == filename)
        ).one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename).filter(Filename.filename == filename).one()

        # Ensure that all of our journal entries have been created
        journals = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [(j.name, j.version, j.action, j.submitted_by) for j in journals] == [
            ("example", None, "create", user),
            ("example", None, f"add Owner {user.username}", user),
            ("example", "1.0", "new release", user),
            ("example", "1.0", "add source file example-1.0.tar.gz", user),
        ]

    def test_upload_succeeds_with_signature(
        self, pyramid_config, db_request, metrics, project_service, monkeypatch
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)

        filename = "{}-{}.tar.gz".format("example", "1.0")

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
                "gpg_signature": "...",
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(legacy, "send_gpg_signature_uploaded_email", send_email)

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200
        assert resp.body == (
            b"GPG signature support has been removed from PyPI and the provided "
            b"signature has been discarded."
        )

        assert send_email.calls == [
            pretend.call(db_request, user, project_name="example"),
        ]

    def test_upload_succeeds_without_two_factor(
        self, pyramid_config, db_request, metrics, project_service, monkeypatch
    ):
        user = UserFactory.create(totp_secret=None)
        EmailFactory.create(user=user)

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename="example-1.0.tar.gz",
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(legacy, "send_two_factor_not_yet_enabled_email", send_email)

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200
        assert resp.body == (
            b"Two factor authentication is not enabled for your account."
        )

        assert send_email.calls == [
            pretend.call(db_request, user),
        ]

    @pytest.mark.parametrize(
        ("emails_verified", "expected_success"),
        [
            ([], False),
            ([True], True),
            ([False], False),
            ([True, True], True),
            ([True, False], True),
            ([False, False], False),
            ([False, True], False),
        ],
    )
    def test_upload_requires_verified_email(
        self,
        pyramid_config,
        db_request,
        emails_verified,
        expected_success,
        metrics,
        project_service,
    ):
        user = UserFactory.create()
        for i, verified in enumerate(emails_verified):
            EmailFactory.create(user=user, verified=verified, primary=i == 0)

        filename = "{}-{}.tar.gz".format("example", "1.0")

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        if expected_success:
            resp = legacy.file_upload(db_request)
            assert resp.status_code == 200
        else:
            db_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

            with pytest.raises(HTTPBadRequest) as excinfo:
                legacy.file_upload(db_request)

            resp = excinfo.value

            assert db_request.help_url.calls == [pretend.call(_anchor="verified-email")]
            assert resp.status_code == 400
            assert resp.status == (
                (
                    "400 User {!r} does not have a verified primary email "
                    "address. Please add a verified primary email before "
                    "attempting to upload to PyPI. See /the/help/url/ for "
                    "more information."
                ).format(user.username)
            )

    def test_upload_purges_legacy(
        self,
        pyramid_config,
        db_request,
        monkeypatch,
        metrics,
        project_service,
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user)

        filename = "{}-{}.tar.gz".format("example", "1.0")

        pyramid_config.testing_securitypolicy(identity=user)
        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "example",
                "version": "1.0",
                "filetype": "sdist",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        storage_service = pretend.stub(store=lambda path, filepath, meta: None)
        db_request.find_service = lambda svc, name=None, context=None: {
            IFileStorage: storage_service,
            IMetricsService: metrics,
            IProjectService: project_service,
        }.get(svc)
        db_request.user_agent = "warehouse-tests/6.6.6"

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

    def test_fails_in_read_only_mode(self, pyramid_request):
        pyramid_request.flags = pretend.stub(enabled=lambda *a: True)

        with pytest.raises(HTTPForbidden) as excinfo:
            legacy.file_upload(pyramid_request)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == ("403 Read-only mode: Uploads are temporarily disabled.")

    def test_fails_without_user(self, pyramid_config, pyramid_request):
        pyramid_request.flags = pretend.stub(enabled=lambda *a: False)
        pyramid_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")
        pyramid_config.testing_securitypolicy(userid=None)

        with pytest.raises(HTTPForbidden) as excinfo:
            legacy.file_upload(pyramid_request)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == (
            "403 Invalid or non-existent authentication information. "
            "See /the/help/url/ for more information."
        )


def test_submit(pyramid_request):
    resp = legacy.submit(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == (
        "410 Project pre-registration is no longer required or supported, "
        "upload your files instead."
    )


def test_doc_upload(pyramid_request):
    resp = legacy.doc_upload(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == (
        "410 Uploading documentation is no longer supported, we recommend "
        "using https://readthedocs.org/."
    )


def test_missing_trailing_slash_redirect(pyramid_request):
    pyramid_request.route_path = pretend.call_recorder(lambda *a, **kw: "/legacy/")

    resp = legacy.missing_trailing_slash_redirect(pyramid_request)

    assert resp.status_code == 308
    assert resp.status == (
        "308 An upload was attempted to /legacy but the expected upload URL is "
        "/legacy/ (with a trailing slash)"
    )
    assert resp.headers["Location"] == "/legacy/"
