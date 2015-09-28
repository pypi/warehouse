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

import io
import os.path
import tempfile

from unittest import mock

import pkg_resources
import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden
from webob.multidict import MultiDict
from wtforms.validators import ValidationError

from warehouse.classifiers.models import Classifier
from warehouse.legacy.api import pypi
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import (
    File, Filename, Dependency, DependencyKind, Release, Project, Role,
)

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory, ReleaseFactory, RoleFactory,
)


def test_exc_with_message():
    exc = pypi._exc_with_message(HTTPBadRequest, "My Test Message.")
    assert isinstance(exc, HTTPBadRequest)
    assert exc.status_code == 400
    assert exc.status == "400 My Test Message."


class TestValidation:

    @pytest.mark.parametrize("version", ["1.0", "30a1", "1!1", "1.0-1"])
    def test_validates_valid_pep440_version(self, version):
        form, field = pretend.stub(), pretend.stub(data=version)
        pypi._validate_pep440_version(form, field)

    @pytest.mark.parametrize("version", ["dog", "1.0.dev.a1", "1.0+local"])
    def test_validates_invalid_pep440_version(self, version):
        form, field = pretend.stub(), pretend.stub(data=version)
        with pytest.raises(ValidationError):
            pypi._validate_pep440_version(form, field)

    @pytest.mark.parametrize(
        ("requirement", "expected"),
        [
            ("foo", ("foo", None)),
            ("foo (>1.0)", ("foo", ">1.0")),
        ],
    )
    def test_parses_legacy_requirement_valid(self, requirement, expected):
        parsed = pypi._parse_legacy_requirement(requirement)
        assert parsed == expected

    @pytest.mark.parametrize("requirement", ["foo bar"])
    def test_parses_legacy_requirement_invalid(self, requirement):
        with pytest.raises(ValueError):
            pypi._parse_legacy_requirement(requirement)

    @pytest.mark.parametrize("specifier", [">=1.0", "<=1.0-1"])
    def test_validates_valid_pep440_specifier(self, specifier):
        pypi._validate_pep440_specifier(specifier)

    @pytest.mark.parametrize("specifier", ["wat?"])
    def test_validates_invalid_pep440_specifier(self, specifier):
        with pytest.raises(ValidationError):
            pypi._validate_pep440_specifier(specifier)

    @pytest.mark.parametrize(
        ("requirement", "specifier"),
        [
            ("foo (>=1.0)", ">=1.0"),
            ("foo", None),
            ("_foo", None),
            ("foo2", None),
        ],
    )
    def test_validates_legacy_non_dist_req_valid(self, monkeypatch,
                                                 requirement, specifier):
        spec_validator = pretend.call_recorder(lambda spec: None)
        monkeypatch.setattr(pypi, "_validate_pep440_specifier", spec_validator)
        pypi._validate_legacy_non_dist_req(requirement)

        if specifier is not None:
            assert spec_validator.calls == [pretend.call(specifier)]
        else:
            assert spec_validator.calls == []

    @pytest.mark.parametrize(
        "requirement",
        [
            "foo-bar (>=1.0)",
            "foo-bar",
            "2foo (>=1.0)",
            "2foo",
            "☃ (>=1.0)",
            "☃",
        ],
    )
    def test_validates_legacy_non_dist_req_invalid(self, monkeypatch,
                                                   requirement):
        spec_validator = pretend.call_recorder(lambda spec: None)
        monkeypatch.setattr(pypi, "_validate_pep440_specifier", spec_validator)

        with pytest.raises(ValidationError):
            pypi._validate_legacy_non_dist_req(requirement)

        assert spec_validator.calls == []

    def test_validate_legacy_non_dist_req_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(pypi, "_validate_legacy_non_dist_req", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        pypi._validate_legacy_non_dist_req_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]

    @pytest.mark.parametrize(
        ("requirement", "specifier"),
        [
            ("foo (>=1.0)", ">=1.0"),
            ("foo", None),
            ("foo2", None),
            ("foo-bar", None),
            ("foo_bar", None),
        ],
    )
    def test_validate_legacy_dist_req_valid(self, monkeypatch, requirement,
                                            specifier):
        spec_validator = pretend.call_recorder(lambda spec: None)
        monkeypatch.setattr(pypi, "_validate_pep440_specifier", spec_validator)
        pypi._validate_legacy_dist_req(requirement)

        if specifier is not None:
            assert spec_validator.calls == [pretend.call(specifier)]
        else:
            assert spec_validator.calls == []

    @pytest.mark.parametrize(
        "requirement",
        [
            "☃ (>=1.0)",
            "☃",
            "foo-",
            "foo- (>=1.0)",
            "_foo",
            "_foo (>=1.0)",
        ],
    )
    def test_validate_legacy_dist_req_invalid(self, monkeypatch, requirement):
        spec_validator = pretend.call_recorder(lambda spec: None)
        monkeypatch.setattr(pypi, "_validate_pep440_specifier", spec_validator)

        with pytest.raises(ValidationError):
            pypi._validate_legacy_dist_req(requirement)

        assert spec_validator.calls == []

    def test_validate_legacy_dist_req_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(pypi, "_validate_legacy_dist_req", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        pypi._validate_legacy_dist_req_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]

    @pytest.mark.parametrize(
        ("requirement", "specifier"),
        [
            ("C", None),
            ("openssl (>=1.0.0)", ">=1.0.0"),
        ],
    )
    def test_validate_requires_external(self, monkeypatch, requirement,
                                        specifier):
        spec_validator = pretend.call_recorder(lambda spec: None)
        monkeypatch.setattr(pypi, "_validate_pep440_specifier", spec_validator)

        pypi._validate_requires_external(requirement)

        if specifier is not None:
            assert spec_validator.calls == [pretend.call(specifier)]
        else:
            assert spec_validator.calls == []

    def test_validate_requires_external_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(pypi, "_validate_requires_external", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        pypi._validate_requires_external_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]

    @pytest.mark.parametrize(
        "project_url",
        [
            "Home, https://pypi.python.org/",
            ("A" * 32) + ", https://example.com/",
        ],
    )
    def test_validate_project_url_valid(self, project_url):
        pypi._validate_project_url(project_url)

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
        ],
    )
    def test_validate_project_url_invalid(self, project_url):
        with pytest.raises(ValidationError):
            pypi._validate_project_url(project_url)

    def test_validate_project_url_list(self, monkeypatch):
        validator = pretend.call_recorder(lambda datum: None)
        monkeypatch.setattr(pypi, "_validate_project_url", validator)

        data = [pretend.stub(), pretend.stub(), pretend.stub()]
        form, field = pretend.stub(), pretend.stub(data=data)
        pypi._validate_project_url_list(form, field)

        assert validator.calls == [pretend.call(datum) for datum in data]


def test_construct_dependencies():
    types = {
        "requires": DependencyKind.requires,
        "provides": DependencyKind.provides,
    }

    form = pretend.stub(
        requires=pretend.stub(data=["foo (>1)"]),
        provides=pretend.stub(data=["bar (>2)"]),
    )

    for dep in pypi._construct_dependencies(form, types):
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
        ],
    )
    def test_processes_form_data(self, data, expected):
        field = pypi.ListField()
        field = field.bind(pretend.stub(meta=pretend.stub()), "formname")
        field.process_formdata(data)
        assert field.data == expected


class TestMetadataForm:

    @pytest.mark.parametrize(
        "data",
        [
            {"filetype": "sdist"},
            {"filetpye": "bdist_wheel", "pyversion": "3.4"},
        ],
    )
    def test_full_validate_valid(self, data):
        form = pypi.MetadataForm(MultiDict(data))
        form.full_validate()

    @pytest.mark.parametrize(
        "data",
        [
            {"filetype": "sdist", "pyversion": "3.4"},
            {"filetype": "bdist_wheel"},
        ],
    )
    def test_full_validate_invalid(self, data):
        form = pypi.MetadataForm(MultiDict(data))
        with pytest.raises(ValidationError):
            form.full_validate()


class TestFileUpload:

    @pytest.mark.parametrize("version", ["2", "3", "-1", "0", "dog", "cat"])
    def test_fails_invalid_version(self, pyramid_config, pyramid_request,
                                   version):
        pyramid_config.testing_securitypolicy(userid=1)
        pyramid_request.POST["protocol_version"] = version

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(pyramid_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Unknown protocol version."

    @pytest.mark.parametrize(
        ("post_data", "message"),
        [
            # metadata_version errors.
            ({}, "metadata_version: This field is required."),
            (
                {"metadata_version": "-1"},
                "metadata_version: Unknown Metadata Version",
            ),

            # name errors.
            ({"metadata_version": "1.2"}, "name: This field is required."),
            (
                {"metadata_version": "1.2", "name": "foo-"},
                "name: Must start and end with a letter or numeral and "
                "contain only ascii numeric and '.', '_' and '-'.",
            ),

            # version errors.
            (
                {"metadata_version": "1.2", "name": "example"},
                "version: This field is required.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "dog",
                },
                "version: Must start and end with a letter or numeral and "
                "contain only ascii numeric and '.', '_' and '-'.",
            ),

            # filetype/pyversion errors.
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                },
                "filetype: This field is required.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "bdist_wat",
                },
                "__all__: Python version is required for binary distribution "
                "uploads.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "bdist_wat",
                    "pyversion": "1.0",
                },
                "filetype: Unknown type of file.",
            ),
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                    "pyversion": "1.0",
                },
                "__all__: The only valid Python version for a sdist is "
                "'source'.",
            ),

            # md5_digest errors.
            (
                {
                    "metadata_version": "1.2",
                    "name": "example",
                    "version": "1.0",
                    "filetype": "sdist",
                },
                "md5_digest: This field is required.",
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
                "summary: Field cannot be longer than 512 characters.",
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
                "summary: Multiple lines are not allowed.",
            ),
        ],
    )
    def test_fails_invalid_post_data(self, pyramid_config, db_request,
                                     post_data, message):
        pyramid_config.testing_securitypolicy(userid=1)
        db_request.POST = MultiDict(post_data)

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 {}".format(message)

    @pytest.mark.parametrize("name", ["requirements.txt", "rrequirements.txt"])
    def test_fails_with_invalid_names(self, pyramid_config, db_request, name):
        pyramid_config.testing_securitypolicy(userid=1)
        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": name,
            "version": "1.0",
            "filetype": "sdist",
            "md5_digest": "a fake md5 digest",
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 The name {!r} is not allowed.".format(name)

    def test_upload_fails_without_file(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)
        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": "example",
            "version": "1.0",
            "filetype": "sdist",
            "md5_digest": "a fake md5 digest",
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Upload payload does not have a file."

    def test_upload_cleans_unknown_values(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)
        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": "UNKNOWN",
            "version": "1.0",
            "filetype": "sdist",
            "md5_digest": "a fake md5 digest",
        })

        with pytest.raises(HTTPBadRequest):
            pypi.file_upload(db_request)

        assert "name" not in db_request.POST

    @pytest.mark.parametrize("has_signature", [True, False])
    def test_successful_upload(self, tmpdir, monkeypatch, pyramid_config,
                               db_request, has_signature):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        pyramid_config.testing_securitypolicy(userid=1)
        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        db_request.db.add(
            Classifier(classifier="Environment :: Other Environment"),
        )

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "pyversion": "source",
            "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
        })
        db_request.POST.extend([
            ("classifiers", "Environment :: Other Environment"),
        ])

        if has_signature:
            db_request.POST["gpg_signature"] = pretend.stub(
                filename=filename + ".asc",
                file=io.BytesIO(
                    b"-----BEGIN PGP SIGNATURE-----\n"
                    b" This is a Fake Signature"
                ),
            )

        @pretend.call_recorder
        def storage_service_store(path, file_path):
            if file_path.endswith(".asc"):
                expected = (
                    b"-----BEGIN PGP SIGNATURE-----\n"
                    b" This is a Fake Signature"
                )
            else:
                expected = b"A fake file."

            with open(file_path, "rb") as fp:
                assert fp.read() == expected

        storage_service = pretend.stub(store=storage_service_store)
        db_request.find_service = pretend.call_recorder(
            lambda svc: storage_service
        )

        resp = pypi.file_upload(db_request)

        assert resp.status_code == 200
        assert db_request.find_service.calls == [pretend.call(IFileStorage)]
        assert len(storage_service.store.calls) == 2 if has_signature else 1
        assert storage_service.store.calls[0] == pretend.call(
            os.path.join(
                "source",
                project.name[0],
                project.name,
                filename,
            ),
            mock.ANY,
        )

        if has_signature:
            assert storage_service.store.calls[1] == pretend.call(
                os.path.join(
                    "source",
                    project.name[0],
                    project.name,
                    filename + ".asc",
                ),
                mock.ANY,
            )

        # Ensure that a File object has been created.
        db_request.db.query(File) \
                     .filter((File.release == release) &
                             (File.filename == filename)) \
                     .one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename) \
                     .filter(Filename.filename == filename).one()

    @pytest.mark.parametrize("sig", [b"lol nope"])
    def test_upload_fails_with_invalid_signature(self, pyramid_config,
                                                 db_request, sig):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
            "gpg_signature": pretend.stub(
                filename=filename + ".asc",
                file=io.BytesIO(sig),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 PGP signature is not ASCII armored."

    def test_upload_fails_with_invalid_classifier(self, pyramid_config,
                                                  db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
        })
        db_request.POST.extend([
            ("classifiers", "Environment :: Other Environment"),
        ])

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 classifiers: 'Environment :: Other Environment' is not a "
            "valid choice for this field"
        )

    def test_upload_fails_with_invalid_hash(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 The MD5 digest supplied does not match a digest calculated "
            "from the uploaded file."
        )

    def test_upload_fails_with_too_large_file(self, pyramid_config,
                                              db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 File too large."

    def test_upload_fails_with_too_large_signature(self, pyramid_config,
                                                   db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "0cc175b9c0f1b6a831c399e269772661",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a"),
            ),
            "gpg_signature": pretend.stub(
                filename=filename + ".asc",
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Signature too large."

    def test_upload_fails_with_previously_used_filename(self, pyramid_config,
                                                        db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        db_request.db.add(Filename(filename=filename))

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 This filename has previously been used, you should use a "
            "different version."
        )

    def test_upload_fails_with_existing_file(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.gz".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        db_request.db.add(File(release=release, filename=filename))

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 File already exists."

    def test_upload_fails_with_wrong_filename(self, pyramid_config,
                                              db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "nope-{}.tar.gz".format(release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == (
            "400 The filename for {!r} must start with {!r}.".format(
                project.name,
                pkg_resources.safe_name(project.name).lower(),
            )
        )

    def test_upload_fails_with_invalid_extension(self, pyramid_config,
                                                 db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.wat".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Invalid file extension."

    @pytest.mark.parametrize("character", ["/", "\\"])
    def test_upload_fails_with_unsafe_filename(self, pyramid_config,
                                               db_request, character):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}.tar.wat".format(
            character + project.name,
            release.version,
        )

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == \
            "400 Cannot upload a file with '/' or '\\' in the name."

    def test_upload_fails_without_permission(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1, permissive=False)

        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")

        filename = "{}-{}.tar.wat".format(project.name, release.version)

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "sdist",
            "md5_digest": "nope!",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"a" * (pypi.MAX_FILESIZE + 1)),
            ),
        })

        with pytest.raises(HTTPForbidden):
            pypi.file_upload(db_request)

    @pytest.mark.parametrize(
        "plat",
        ["any", "win32", "win-amd64", "win_amd64", "win-ia64", "win_ia64"],
    )
    def test_upload_succeeds_with_wheel(self, tmpdir, monkeypatch,
                                        pyramid_config, db_request, plat):
        monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}-cp34-none-{}.whl".format(
            project.name,
            release.version,
            plat,
        )

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "bdist_wheel",
            "pyversion": "cp34",
            "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
        })

        @pretend.call_recorder
        def storage_service_store(path, file_path):
            with open(file_path, "rb") as fp:
                assert fp.read() == b"A fake file."

        storage_service = pretend.stub(store=storage_service_store)
        db_request.find_service = pretend.call_recorder(
            lambda svc: storage_service
        )

        resp = pypi.file_upload(db_request)

        assert resp.status_code == 200
        assert db_request.find_service.calls == [pretend.call(IFileStorage)]
        assert storage_service.store.calls == [
            pretend.call(
                os.path.join(
                    "cp34",
                    project.name[0],
                    project.name,
                    filename,
                ),
                mock.ANY,
            ),
        ]

        # Ensure that a File object has been created.
        db_request.db.query(File) \
                     .filter((File.release == release) &
                             (File.filename == filename)) \
                     .one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename) \
                     .filter(Filename.filename == filename).one()

    @pytest.mark.parametrize("plat", ["linux_x86_64", "linux_x86_64.win32"])
    def test_upload_fails_with_unsupported_wheel_plat(self, pyramid_config,
                                                      db_request, plat):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        RoleFactory.create(user=user, project=project)

        filename = "{}-{}-cp34-none-{}.whl".format(
            project.name,
            release.version,
            plat,
        )

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": release.version,
            "filetype": "bdist_wheel",
            "pyversion": "cp34",
            "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
        })

        with pytest.raises(HTTPBadRequest) as excinfo:
            pypi.file_upload(db_request)

        resp = excinfo.value

        assert resp.status_code == 400
        assert resp.status == "400 Binary wheel for an unsupported platform."

    def test_upload_succeeds_creates_release(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project)

        db_request.db.add(
            Classifier(classifier="Environment :: Other Environment"),
        )
        db_request.db.add(
            Classifier(classifier="Programming Language :: Python"),
        )

        filename = "{}-{}.tar.gz".format(project.name, "1.0")

        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": project.name,
            "version": "1.0",
            "summary": "This is my summary!",
            "filetype": "sdist",
            "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
        })
        db_request.POST.extend([
            ("classifiers", "Environment :: Other Environment"),
            ("classifiers", "Programming Language :: Python"),
            ("requires_dist", "foo"),
            ("requires_dist", "bar (>1.0)"),
            ("project_urls", "Test, https://example.com/"),
            ("requires_external", "Cheese (>1.0)"),
            ("provides", "testing"),
        ])

        storage_service = pretend.stub(store=lambda path, content: None)
        db_request.find_service = lambda svc: storage_service

        resp = pypi.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Release object has been created.
        release = (
            db_request.db.query(Release)
                         .filter((Release.project == project) &
                                 (Release.version == "1.0"))
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

        # Ensure that a File object has been created.
        db_request.db.query(File) \
                     .filter((File.release == release) &
                             (File.filename == filename)) \
                     .one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename) \
                     .filter(Filename.filename == filename).one()

    def test_upload_succeeds_creates_project(self, pyramid_config, db_request):
        pyramid_config.testing_securitypolicy(userid=1)

        user = UserFactory.create()

        filename = "{}-{}.tar.gz".format("example", "1.0")

        db_request.user = user
        db_request.POST = MultiDict({
            "metadata_version": "1.2",
            "name": "example",
            "version": "1.0",
            "filetype": "sdist",
            "md5_digest": "335c476dc930b959dda9ec82bd65ef19",
            "content": pretend.stub(
                filename=filename,
                file=io.BytesIO(b"A fake file."),
            ),
        })

        storage_service = pretend.stub(store=lambda path, content: None)
        db_request.find_service = lambda svc: storage_service

        resp = pypi.file_upload(db_request)

        assert resp.status_code == 200

        # Ensure that a Project object has been created.
        project = (
            db_request.db.query(Project)
                         .filter(Project.name == "example")
                         .one()
        )

        # Ensure that a Role with the user as owner has been created.
        role = db_request.db.query(Role) \
                            .filter((Role.user == user) &
                                    (Role.project == project)) \
                            .one()
        assert role.role_name == "Owner"

        # Ensure that a Release object has been created.
        release = (
            db_request.db.query(Release)
                         .filter((Release.project == project) &
                                 (Release.version == "1.0"))
                         .one()
        )

        # Ensure that a File object has been created.
        db_request.db.query(File) \
                     .filter((File.release == release) &
                             (File.filename == filename)) \
                     .one()

        # Ensure that a Filename object has been created.
        db_request.db.query(Filename) \
                     .filter(Filename.filename == filename).one()

    def test_fails_without_user(self, pyramid_config, pyramid_request):
        pyramid_config.testing_securitypolicy(userid=None)

        with pytest.raises(HTTPForbidden) as excinfo:
            pypi.file_upload(pyramid_request)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == (
            "403 Invalid or non-existent authentication information."
        )


def test_submit(pyramid_request):
    resp = pypi.submit(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == \
        "410 This API is no longer supported, instead simply upload the file."


def test_doc_upload(pyramid_request):
    resp = pypi.doc_upload(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == (
        "410 Uploading documentation is no longer supported, we recommend "
        "using https://readthedocs.org/."
    )


def test_doap(pyramid_request):
    resp = pypi.doap(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == "410 DOAP is no longer supported."


def test_forbidden_legacy():
    exc, request = pretend.stub(), pretend.stub()
    resp = pypi.forbidden_legacy(exc, request)
    assert resp is exc
