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

import pkg_resources
import pretend
import pytest
import requests

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from trove_classifiers import classifiers
from webob.multidict import MultiDict
from wtforms.form import Form
from wtforms.validators import ValidationError

from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.admin.squats import Squat
from warehouse.classifiers.models import Classifier
from warehouse.forklift import legacy
from warehouse.metrics import IMetricsService
from warehouse.packaging.interfaces import IFileStorage
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

from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.classifiers import ClassifierFactory
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


_TAR_GZ_PKG_TESTDATA = _get_tar_testdata("gz")
_TAR_GZ_PKG_MD5 = hashlib.md5(_TAR_GZ_PKG_TESTDATA).hexdigest()
_TAR_GZ_PKG_SHA256 = hashlib.sha256(_TAR_GZ_PKG_TESTDATA).hexdigest()
_TAR_GZ_PKG_STORAGE_HASH = hashlib.blake2b(
    _TAR_GZ_PKG_TESTDATA, digest_size=256 // 8
).hexdigest()

_TAR_BZ2_PKG_TESTDATA = _get_tar_testdata("bz2")
_TAR_BZ2_PKG_MD5 = hashlib.md5(_TAR_BZ2_PKG_TESTDATA).hexdigest()
_TAR_BZ2_PKG_SHA256 = hashlib.sha256(_TAR_BZ2_PKG_TESTDATA).hexdigest()
_TAR_BZ2_PKG_STORAGE_HASH = hashlib.blake2b(
    _TAR_BZ2_PKG_TESTDATA, digest_size=256 // 8
).hexdigest()


def test_exc_with_message():
    exc = legacy._exc_with_message(HTTPBadRequest, "My Test Message.")
    assert isinstance(exc, HTTPBadRequest)
    assert exc.status_code == 400
    assert exc.status == "400 My Test Message."


class TestValidation:
    @pytest.mark.parametrize("version", ["1.0", "30a1", "1!1", "1.0-1"])
    def test_validates_valid_pep440_version(self, version):
        form, field = pretend.stub(), pretend.stub(data=version)
        legacy._validate_pep440_version(form, field)

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
        ["Home, https://pypi.python.org/", ("A" * 32) + ", https://example.com/"],
    )
    def test_validate_project_url_valid(self, project_url):
        legacy._validate_project_url(project_url)

    @pytest.mark.parametrize(
        "project_url",
        [
            "Home,https://pypi.python.org/",
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
            {"filetype": "sdist", "md5_digest": "bad"},
            {"filetpye": "bdist_wheel", "pyversion": "3.4", "md5_digest": "bad"},
            {"filetype": "sdist", "sha256_digest": "bad"},
            {"filetpye": "bdist_wheel", "pyversion": "3.4", "sha256_digest": "bad"},
            {"filetype": "sdist", "md5_digest": "bad", "sha256_digest": "bad"},
            {
                "filetpye": "bdist_wheel",
                "pyversion": "3.4",
                "md5_digest": "bad",
                "sha256_digest": "bad",
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
        [("test.exe", "bdist_msi"), ("test.msi", "bdist_wininst")],
    )
    def test_bails_with_invalid_package_type(self, filename, filetype):
        assert not legacy._is_valid_dist_file(filename, filetype)

    @pytest.mark.parametrize(
        ("filename", "filetype"),
        [
            ("test.exe", "bdist_wininst"),
            ("test.zip", "sdist"),
            ("test.egg", "bdist_egg"),
            ("test.whl", "bdist_wheel"),
        ],
    )
    def test_bails_with_invalid_zipfile(self, tmpdir, filename, filetype):
        f = str(tmpdir.join(filename))

        with open(f, "wb") as fp:
            fp.write(b"this isn't a valid zip file")

        assert not legacy._is_valid_dist_file(f, filetype)

    @pytest.mark.parametrize(
        "filename", ["test.tar", "test.tar.gz", "test.tgz", "test.tar.bz2", "test.tbz2"]
    )
    def test_bails_with_invalid_tarfile(self, tmpdir, filename):
        fake_tar = str(tmpdir.join(filename))

        with open(fake_tar, "wb") as fp:
            fp.write(b"Definitely not a valid tar file.")

        assert not legacy._is_valid_dist_file(fake_tar, "sdist")

    @pytest.mark.parametrize("compression", ("", "gz", "bz2"))
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

    @pytest.mark.parametrize("compression", ("", "gz", "bz2"))
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

    def test_wininst_unsafe_filename(self, tmpdir):
        f = str(tmpdir.join("test.exe"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("something/bar.py", b"the test file")

        assert not legacy._is_valid_dist_file(f, "bdist_wininst")

    def test_wininst_safe_filename(self, tmpdir):
        f = str(tmpdir.join("test.exe"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("purelib/bar.py", b"the test file")

        assert legacy._is_valid_dist_file(f, "bdist_wininst")

    def test_msi_invalid_header(self, tmpdir):
        f = str(tmpdir.join("test.msi"))

        with open(f, "wb") as fp:
            fp.write(b"this isn't the correct header for an msi")

        assert not legacy._is_valid_dist_file(f, "bdist_msi")

    def test_msi_valid_header(self, tmpdir):
        f = str(tmpdir.join("test.msi"))

        with open(f, "wb") as fp:
            fp.write(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1")

        assert legacy._is_valid_dist_file(f, "bdist_msi")

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

    def test_egg_no_pkg_info(self, tmpdir):
        f = str(tmpdir.join("test.egg"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("something.txt", b"Just a placeholder file")

        assert not legacy._is_valid_dist_file(f, "bdist_egg")

    def test_egg_has_pkg_info(self, tmpdir):
        f = str(tmpdir.join("test.egg"))

        with zipfile.ZipFile(f, "w") as zfp:
            zfp.writestr("something.txt", b"Just a placeholder file")
            zfp.writestr("PKG-INFO", b"this is the package info")

        assert legacy._is_valid_dist_file(f, "bdist_egg")

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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }
        db_request.db.add(
            File(
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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
        requested_file_name = "{}-{}-1.tar.gz".format(project.name, release.version)
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }
        db_request.db.add(
            File(
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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
        requested_file_name = "{}-{}-1.tar.gz".format(project.name, release.version)
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }
        db_request.db.add(
            File(
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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)
        file_value = file_content.getvalue()

        hashes = {
            "sha256": hashlib.sha256(file_value).hexdigest(),
            "md5": hashlib.md5(file_value).hexdigest(),
            "blake2_256": hashlib.blake2b(file_value, digest_size=256 // 8).hexdigest(),
        }

        wrong_hashes = {"sha256": "nah", "md5": "nope", "blake2_256": "nuh uh"}

        db_request.db.add(
            File(
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
        pyramid_config.testing_securitypolicy(userid=1)
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
        pyramid_config.testing_securitypolicy(userid=1)
        pyramid_request.POST["protocol_version"] = version
        pyramid_request.flags = pretend.stub(enabled=lambda *a: False)

        pyramid_request.user = pretend.stub(primary_email=pretend.stub(verified=True))

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
                "'" + "A" * 513 + "' is an invalid value for Summary. "
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
    def test_fails_invalid_post_data(
        self, pyramid_config, db_request, post_data, message
    ):
        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
        db_request.user = user
        db_request.POST = MultiDict(post_data)

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 {}".format(message)

    @pytest.mark.parametrize("name", ["requirements.txt", "rrequirements.txt"])
    def test_fails_with_invalid_names(self, pyramid_config, db_request, name):
        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
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
        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
        db_request.user = user
        db_request.remote_addr = "10.10.10.30"
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
        db_request.user = user
        pyramid_config.testing_securitypolicy(userid=1)
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
            (
                "400 The name {!r} isn't allowed (conflict "
                "with Python Standard Library module name). "
                "See /the/help/url/ "
                "for more information."
            )
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
        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
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
        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
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
        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
        db_request.user = user
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
        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
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
        ("has_signature", "digests"),
        [
            (True, {"md5_digest": _TAR_GZ_PKG_MD5}),
            (True, {"sha256_digest": _TAR_GZ_PKG_SHA256}),
            (False, {"md5_digest": _TAR_GZ_PKG_MD5}),
            (False, {"sha256_digest": _TAR_GZ_PKG_SHA256}),
            (
                True,
                {"md5_digest": _TAR_GZ_PKG_MD5, "sha256_digest": _TAR_GZ_PKG_SHA256},
            ),
            (
                False,
                {"md5_digest": _TAR_GZ_PKG_MD5, "sha256_digest": _TAR_GZ_PKG_SHA256},
            ),
        ],
    )
    def test_successful_upload(
        self,
        tmpdir,
        monkeypatch,
        pyramid_config,
        db_request,
        has_signature,
        digests,
        metrics,
    ):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        db_request.db.add(Classifier(classifier="Environment :: Other Environment"))

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.user = user
        db_request.remote_addr = "10.10.10.40"
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

        if has_signature:
            gpg_signature = FieldStorage()
            gpg_signature.filename = filename + ".asc"
            gpg_signature.file = io.BytesIO(
                b"-----BEGIN PGP SIGNATURE-----\n" b" This is a Fake Signature"
            )
            db_request.POST["gpg_signature"] = gpg_signature
            assert isinstance(db_request.POST["gpg_signature"], FieldStorage)

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            if file_path.endswith(".asc"):
                expected = (
                    b"-----BEGIN PGP SIGNATURE-----\n" b" This is a Fake Signature"
                )
            else:
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

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200
        assert db_request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IFileStorage),
        ]
        assert len(storage_service.store.calls) == 2 if has_signature else 1
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

        if has_signature:
            assert storage_service.store.calls[1] == pretend.call(
                "/".join(
                    [
                        _TAR_GZ_PKG_STORAGE_HASH[:2],
                        _TAR_GZ_PKG_STORAGE_HASH[2:4],
                        _TAR_GZ_PKG_STORAGE_HASH[4:],
                        filename + ".asc",
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
            .options(joinedload("submitted_by"))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [
            (j.name, j.version, j.action, j.submitted_by, j.submitted_from)
            for j in journals
        ] == [
            (
                release.project.name,
                release.version,
                "add source file {}".format(filename),
                user,
                "10.10.10.40",
            )
        ]

        assert metrics.increment.calls == [
            pretend.call("warehouse.upload.attempt"),
            pretend.call("warehouse.upload.ok", tags=["filetype:sdist"]),
        ]

    @pytest.mark.parametrize("content_type", [None, "image/foobar"])
    def test_upload_fails_invlaid_content_type(
        self, tmpdir, monkeypatch, pyramid_config, db_request, content_type
    ):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        EmailFactory.create(user=user)
        db_request.user = user
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        db_request.db.add(Classifier(classifier="Environment :: Other Environment"))

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        db_request.user = user
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        db_request.user = user
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.bz2".format(project.name, release.version)

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
            "400 Invalid file extension: Use .egg, .tar.gz, .whl or .zip "
            "extension. See https://www.python.org/dev/peps/pep-0527 "
            "for more information."
        )

    def test_upload_fails_for_second_sdist(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        FileFactory.create(
            release=release,
            packagetype="sdist",
            filename="{}-{}.tar.gz".format(project.name, release.version),
        )
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.zip".format(project.name, release.version)

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

    @pytest.mark.parametrize("sig", [b"lol nope"])
    def test_upload_fails_with_invalid_signature(self, pyramid_config, db_request, sig):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
                "gpg_signature": pretend.stub(
                    filename=filename + ".asc", file=io.BytesIO(sig)
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 PGP signature isn't ASCII armored."

    def test_upload_fails_with_invalid_classifier(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)
        classifier = ClassifierFactory(classifier="AA :: BB")

        monkeypatch.setattr(legacy, "deprecated_classifiers", deprecated_classifiers)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.zip".format(project.name, release.version)

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

    def test_upload_fails_with_too_large_file(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create(
            name="foobar", upload_limit=(60 * 1024 * 1024)  # 60 MB
        )
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
            "400 File too large. Limit for project 'foobar' is 60 MB. "
            "See /the/help/url/ for more information."
        )

    def test_upload_fails_with_too_large_project_size_default_limit(
        self, pyramid_config, db_request
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create(
            name="foobar",
            upload_limit=legacy.MAX_FILESIZE,
            total_size=legacy.MAX_PROJECT_SIZE - 1,
        )
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
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

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
        self, pyramid_config, db_request, metrics
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
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
        }.get(svc)
        db_request.remote_addr = "10.10.10.10"
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
            .options(joinedload("submitted_by"))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [
            (j.name, j.version, j.action, j.submitted_by, j.submitted_from)
            for j in journals
        ] == [
            ("example", None, "create", user, "10.10.10.10"),
            (
                "example",
                None,
                "add Owner {}".format(user.username),
                user,
                "10.10.10.10",
            ),
            ("example", "1.0", "new release", user, "10.10.10.10"),
            (
                "example",
                "1.0",
                "add source file example-1.0.tar.gz",
                user,
                "10.10.10.10",
            ),
        ]

    def test_upload_fails_with_too_large_signature(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

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
                "gpg_signature": pretend.stub(
                    filename=filename + ".asc",
                    file=io.BytesIO(b"a" * (legacy.MAX_FILESIZE + 1)),
                ),
            }
        )

        with pytest.raises(HTTPBadRequest) as excinfo:
            legacy.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Signature too large."

    def test_upload_fails_with_previously_used_filename(
        self, pyramid_config, db_request
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
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
            File(
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

        assert resp.status_code == 200

    def test_upload_fails_with_existing_filename_diff_content(
        self, pyramid_config, db_request
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
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
            File(
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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)
        file_content = io.BytesIO(_TAR_GZ_PKG_TESTDATA)

        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "sdist",
                "md5_digest": hashlib.md5(file_content.getvalue()).hexdigest(),
                "content": pretend.stub(
                    filename="{}-fake.tar.gz".format(project.name),
                    file=file_content,
                    type="application/tar",
                ),
            }
        )

        db_request.db.add(
            File(
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

    def test_upload_fails_with_wrong_filename(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "nope-{}.tar.gz".format(release.version)

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
            "400 Start filename for {!r} with {!r}.".format(
                project.name, pkg_resources.safe_name(project.name).lower()
            )
        )

    def test_upload_fails_with_invalid_extension(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.wat".format(project.name, release.version)

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
            "400 Invalid file extension: Use .egg, .tar.gz, .whl or .zip "
            "extension. See https://www.python.org/dev/peps/pep-0527 "
            "for more information."
        )

    @pytest.mark.parametrize("character", ["/", "\\"])
    def test_upload_fails_with_unsafe_filename(
        self, pyramid_config, db_request, character
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.wat".format(character + project.name, release.version)

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

    def test_upload_fails_without_permission(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1, permissive=False)

        user1 = UserFactory.create()
        EmailFactory.create(user=user1)
        user2 = UserFactory.create()
        EmailFactory.create(user=user2)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user1, project=project)

        filename = "{}-{}.tar.wat".format(project.name, release.version)

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
            "403 The user '{0}' "
            "isn't allowed to upload to project '{1}'. "
            "See /the/help/url/ for more information."
        ).format(user2.username, project.name)

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
            "macosx_10_6_intel",
            "macosx_10_13_x86_64",
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

        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}-cp34-none-{}.whl".format(project.name, release.version, plat)

        db_request.user = user
        db_request.remote_addr = "10.10.10.30"
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": release.version,
                "filetype": "bdist_wheel",
                "pyversion": "cp34",
                "md5_digest": _TAR_GZ_PKG_MD5,
                "content": pretend.stub(
                    filename=filename,
                    file=io.BytesIO(_TAR_GZ_PKG_TESTDATA),
                    type="application/tar",
                ),
            }
        )

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            with open(file_path, "rb") as fp:
                assert fp.read() == _TAR_GZ_PKG_TESTDATA

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
            pretend.call(IFileStorage),
        ]
        assert storage_service.store.calls == [
            pretend.call(
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
                    "package-type": "bdist_wheel",
                    "python-version": "cp34",
                },
            )
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
            .options(joinedload("submitted_by"))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [
            (j.name, j.version, j.action, j.submitted_by, j.submitted_from)
            for j in journals
        ] == [
            (
                release.project.name,
                release.version,
                "add cp34 file {}".format(filename),
                user,
                "10.10.10.30",
            )
        ]

        assert metrics.increment.calls == [
            pretend.call("warehouse.upload.attempt"),
            pretend.call("warehouse.upload.ok", tags=["filetype:bdist_wheel"]),
        ]

    def test_upload_succeeds_with_wheel_after_sdist(
        self, tmpdir, monkeypatch, pyramid_config, db_request, metrics
    ):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        FileFactory.create(
            release=release,
            packagetype="sdist",
            filename="{}-{}.tar.gz".format(project.name, release.version),
        )
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}-cp34-none-any.whl".format(project.name, release.version)

        db_request.user = user
        db_request.remote_addr = "10.10.10.30"
        db_request.user_agent = "warehouse-tests/6.6.6"
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

        @pretend.call_recorder
        def storage_service_store(path, file_path, *, meta):
            with open(file_path, "rb") as fp:
                assert fp.read() == b"A fake file."

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
            pretend.call(IFileStorage),
        ]
        assert storage_service.store.calls == [
            pretend.call(
                "/".join(
                    [
                        "4e",
                        "6e",
                        "fa4c0ee2bbad071b4f5b5ea68f1aea89fa716e7754eb13e2314d45a5916e",
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
            )
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
            .options(joinedload("submitted_by"))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [
            (j.name, j.version, j.action, j.submitted_by, j.submitted_from)
            for j in journals
        ] == [
            (
                release.project.name,
                release.version,
                "add cp34 file {}".format(filename),
                user,
                "10.10.10.30",
            )
        ]

    @pytest.mark.parametrize("plat", ["linux_x86_64", "linux_x86_64.win32"])
    def test_upload_fails_with_unsupported_wheel_plat(
        self, monkeypatch, pyramid_config, db_request, plat
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        db_request.user = user
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}-cp34-none-{}.whl".format(project.name, release.version, plat)

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

    def test_upload_updates_existing_project_name(
        self, pyramid_config, db_request, metrics
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create(name="Package-Name")
        RoleFactory.create(user=user, project=project)

        new_project_name = "package-name"
        filename = "{}-{}.tar.gz".format(new_project_name, "1.1")

        db_request.user = user
        db_request.remote_addr = "10.10.10.20"
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
        db_request.remote_addr = "10.10.10.10"
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

    def test_upload_succeeds_creates_release(self, pyramid_config, db_request, metrics):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)

        db_request.db.add(Classifier(classifier="Environment :: Other Environment"))
        db_request.db.add(Classifier(classifier="Programming Language :: Python"))

        filename = "{}-{}.tar.gz".format(project.name, "1.0")

        db_request.user = user
        db_request.remote_addr = "10.10.10.20"
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": "1.0",
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

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Release object has been created.
        release = (
            db_request.db.query(Release)
            .filter((Release.project == project) & (Release.version == "1.0"))
            .one()
        )
        assert release.summary == "This is my summary!"
        assert release.classifiers == [
            "Environment :: Other Environment",
            "Programming Language :: Python",
        ]
        assert set(release.requires_dist) == {"foo", "bar (>1.0)"}
        assert set(release.project_urls) == {"Test, https://example.com/"}
        assert set(release.requires_external) == {"Cheese (>1.0)"}
        assert set(release.provides) == {"testing"}
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
            .options(joinedload("submitted_by"))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [
            (j.name, j.version, j.action, j.submitted_by, j.submitted_from)
            for j in journals
        ] == [
            (release.project.name, release.version, "new release", user, "10.10.10.20"),
            (
                release.project.name,
                release.version,
                "add source file {}".format(filename),
                user,
                "10.10.10.20",
            ),
        ]

    def test_upload_succeeds_creates_classifier(
        self, pyramid_config, db_request, metrics, monkeypatch
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)

        monkeypatch.setattr(legacy, "classifiers", {"AA :: BB", "CC :: DD"})

        db_request.db.add(Classifier(classifier="AA :: BB"))

        filename = "{}-{}.tar.gz".format(project.name, "1.0")

        db_request.user = user
        db_request.remote_addr = "10.10.10.20"
        db_request.user_agent = "warehouse-tests/6.6.6"
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": project.name,
                "version": "1.0",
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
                ("classifiers", "AA :: BB"),
                ("classifiers", "CC :: DD"),
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

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a new Classifier has been created
        classifier = (
            db_request.db.query(Classifier)
            .filter(Classifier.classifier == "CC :: DD")
            .one()
        )
        assert classifier.classifier == "CC :: DD"

        # Ensure that the Release has the new classifier
        release = (
            db_request.db.query(Release)
            .filter((Release.project == project) & (Release.version == "1.0"))
            .one()
        )
        assert release.classifiers == ["AA :: BB", "CC :: DD"]

    def test_all_valid_classifiers_can_be_created(self, db_request):
        for classifier in classifiers:
            db_request.db.add(Classifier(classifier=classifier))
        db_request.db.commit()

    @pytest.mark.parametrize(
        "parent_classifier", ["private", "Private", "PrIvAtE"],
    )
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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        db_request.user = user
        db_request.remote_addr = "10.10.10.20"
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
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)
        project = ProjectFactory.create()
        release_a = ReleaseFactory.create(project=project, version="1.0")
        release_b = ReleaseFactory.create(project=project, version="1.0.0")
        RoleFactory.create(user=user, project=project)

        db_request.user = user
        db_request.remote_addr = "10.10.10.20"
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

    def test_upload_succeeds_creates_project(self, pyramid_config, db_request, metrics):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)

        filename = "{}-{}.tar.gz".format("example", "1.0")

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
        }.get(svc)
        db_request.remote_addr = "10.10.10.10"
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
            .options(joinedload("submitted_by"))
            .order_by("submitted_date", "id")
            .all()
        )
        assert [
            (j.name, j.version, j.action, j.submitted_by, j.submitted_from)
            for j in journals
        ] == [
            ("example", None, "create", user, "10.10.10.10"),
            (
                "example",
                None,
                "add Owner {}".format(user.username),
                user,
                "10.10.10.10",
            ),
            ("example", "1.0", "new release", user, "10.10.10.10"),
            (
                "example",
                "1.0",
                "add source file example-1.0.tar.gz",
                user,
                "10.10.10.10",
            ),
        ]

    def test_upload_succeeds_creates_squats(self, pyramid_config, db_request, metrics):
        pyramid_config.testing_securitypolicy(userid=1)

        squattee = ProjectFactory(name="example")
        user = UserFactory.create()
        EmailFactory.create(user=user)

        filename = "{}-{}.tar.gz".format("exmaple", "1.0")

        db_request.user = user
        db_request.POST = MultiDict(
            {
                "metadata_version": "1.2",
                "name": "exmaple",
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
        db_request.remote_addr = "10.10.10.10"
        db_request.user_agent = "warehouse-tests/6.6.6"

        resp = legacy.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Project object has been created.
        squatter = db_request.db.query(Project).filter(Project.name == "exmaple").one()

        # Ensure that a Squat object has been created.
        squat = db_request.db.query(Squat).one()

        assert squat.squattee == squattee
        assert squat.squatter == squatter
        assert squat.reviewed is False

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
        self, pyramid_config, db_request, emails_verified, expected_success, metrics
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        for i, verified in enumerate(emails_verified):
            EmailFactory.create(user=user, verified=verified, primary=i == 0)

        filename = "{}-{}.tar.gz".format("example", "1.0")

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
        }.get(svc)
        db_request.remote_addr = "10.10.10.10"
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
        self, pyramid_config, db_request, monkeypatch, metrics
    ):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        EmailFactory.create(user=user)

        filename = "{}-{}.tar.gz".format("example", "1.0")

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
        }.get(svc)
        db_request.remote_addr = "10.10.10.10"
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


@pytest.mark.parametrize("status", [True, False])
def test_legacy_purge(monkeypatch, status):
    post = pretend.call_recorder(lambda *a, **kw: None)
    monkeypatch.setattr(requests, "post", post)

    legacy._legacy_purge(status, 1, 2, three=4)

    if status:
        assert post.calls == [pretend.call(1, 2, three=4)]
    else:
        assert post.calls == []


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
