# SPDX-License-Identifier: Apache-2.0

import hashlib
import tempfile

import pretend

from warehouse.packaging.interfaces import ISimpleStorage
from warehouse.packaging.utils import (
    _simple_detail,
    _valid_simple_detail_context,
    render_simple_detail,
)

from ...common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


def test_simple_detail_empty_string(db_request):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project, version="1.0", requires_python="")
    FileFactory.create(release=release)

    db_request.route_url = lambda *a, **kw: "the-url"
    expected_content = _simple_detail(project, db_request)

    assert expected_content["files"][0]["requires-python"] is None


def test_render_simple_detail(db_request, monkeypatch, jinja):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="dog")
    FileFactory.create(release=release1)
    FileFactory.create(
        release=release2, metadata_file_sha256_digest="beefdeadbeefdeadbeefdeadbeefdead"
    )

    fake_hasher = pretend.stub(
        update=pretend.call_recorder(lambda x: None),
        hexdigest=pretend.call_recorder(lambda: "deadbeefdeadbeefdeadbeefdeadbeef"),
    )
    fakeblake2b = pretend.call_recorder(lambda *a, **kw: fake_hasher)
    monkeypatch.setattr(hashlib, "blake2b", fakeblake2b)

    db_request.route_url = lambda *a, **kw: "the-url"
    template = jinja.get_template("templates/api/simple/detail.html")
    context = _simple_detail(project, db_request)
    context = _valid_simple_detail_context(context)
    expected_content = template.render(**context, request=db_request).encode("utf-8")

    content_hash, path = render_simple_detail(project, db_request)

    assert fakeblake2b.calls == [pretend.call(digest_size=32)]
    assert fake_hasher.update.calls == [pretend.call(expected_content)]
    assert fake_hasher.hexdigest.calls == [pretend.call()]

    assert content_hash == "deadbeefdeadbeefdeadbeefdeadbeef"
    assert path == (
        f"{project.normalized_name}/deadbeefdeadbeefdeadbeefdeadbeef"
        + f".{project.normalized_name}.html"
    )


def test_render_simple_detail_with_store(db_request, monkeypatch, jinja):
    project = ProjectFactory.create()

    storage_service = pretend.stub(
        store=pretend.call_recorder(
            lambda path, file_path, *, meta=None: f"http://files/sponsorlogos/{path}"
        )
    )
    db_request.find_service = pretend.call_recorder(
        lambda svc, name=None, context=None: {
            ISimpleStorage: storage_service,
        }.get(svc)
    )

    fake_hasher = pretend.stub(
        update=pretend.call_recorder(lambda x: None),
        hexdigest=pretend.call_recorder(lambda: "deadbeefdeadbeefdeadbeefdeadbeef"),
    )
    fakeblake2b = pretend.call_recorder(lambda *a, **kw: fake_hasher)
    monkeypatch.setattr(hashlib, "blake2b", fakeblake2b)

    fake_named_temporary_file = pretend.stub(
        name="/tmp/wutang",
        write=pretend.call_recorder(lambda data: None),
        flush=pretend.call_recorder(lambda: None),
    )

    class FakeNamedTemporaryFile:
        def __init__(self):
            return None

        def __enter__(self):
            return fake_named_temporary_file

        def __exit__(self, type, value, traceback):
            pass

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", FakeNamedTemporaryFile)

    template = jinja.get_template("templates/api/simple/detail.html")
    context = _simple_detail(project, db_request)
    context = _valid_simple_detail_context(context)
    expected_content = template.render(**context, request=db_request).encode("utf-8")

    content_hash, path = render_simple_detail(project, db_request, store=True)

    assert fake_named_temporary_file.write.calls == [pretend.call(expected_content)]
    assert fake_named_temporary_file.flush.calls == [pretend.call()]

    assert fakeblake2b.calls == [pretend.call(digest_size=32)]
    assert fake_hasher.update.calls == [pretend.call(expected_content)]
    assert fake_hasher.hexdigest.calls == [pretend.call()]

    assert storage_service.store.calls == [
        pretend.call(
            (
                f"{project.normalized_name}/deadbeefdeadbeefdeadbeefdeadbeef"
                + f".{project.normalized_name}.html"
            ),
            "/tmp/wutang",
            meta={
                "project": project.normalized_name,
                "pypi-last-serial": project.last_serial,
                "hash": "deadbeefdeadbeefdeadbeefdeadbeef",
            },
        ),
        pretend.call(
            f"{project.normalized_name}/index.html",
            "/tmp/wutang",
            meta={
                "project": project.normalized_name,
                "pypi-last-serial": project.last_serial,
                "hash": "deadbeefdeadbeefdeadbeefdeadbeef",
            },
        ),
    ]

    assert content_hash == "deadbeefdeadbeefdeadbeefdeadbeef"
    assert path == (
        f"{project.normalized_name}/deadbeefdeadbeefdeadbeefdeadbeef"
        + f".{project.normalized_name}.html"
    )
