# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import os

from warehouse.packaging.interfaces import ISimpleStorage
from warehouse.packaging.services import LocalSimpleStorage
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


def test_render_simple_detail(db_request, jinja):
    project = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project, version="1.0")
    release2 = ReleaseFactory.create(project=project, version="dog")
    FileFactory.create(release=release1)
    FileFactory.create(
        release=release2, metadata_file_sha256_digest="beefdeadbeefdeadbeefdeadbeefdead"
    )

    db_request.route_url = lambda *a, **kw: "the-url"
    template = jinja.get_template("templates/api/simple/detail.html")
    context = _simple_detail(project, db_request)
    context = _valid_simple_detail_context(context)
    expected_content = template.render(**context, request=db_request).encode("utf-8")
    expected_hash = hashlib.blake2b(expected_content, digest_size=32).hexdigest()

    content_hash, path = render_simple_detail(project, db_request)

    assert content_hash == expected_hash
    assert path == (
        f"{project.normalized_name}/{expected_hash}.{project.normalized_name}.html"
    )


def test_render_simple_detail_with_store(db_request, pyramid_services, jinja, tmpdir):
    project = ProjectFactory.create()

    storage_dir = str(tmpdir.join("simple"))
    pyramid_services.register_service(
        LocalSimpleStorage(storage_dir), ISimpleStorage, None, name=""
    )

    template = jinja.get_template("templates/api/simple/detail.html")
    context = _simple_detail(project, db_request)
    context = _valid_simple_detail_context(context)
    expected_content = template.render(**context, request=db_request).encode("utf-8")
    expected_hash = hashlib.blake2b(expected_content, digest_size=32).hexdigest()
    expected_meta = {
        "project": project.normalized_name,
        "pypi-last-serial": project.last_serial,
        "hash": expected_hash,
    }

    content_hash, path = render_simple_detail(project, db_request, store=True)

    assert content_hash == expected_hash
    assert path == (
        f"{project.normalized_name}/{expected_hash}.{project.normalized_name}.html"
    )

    index_path = os.path.join(project.normalized_name, "index.html")
    for stored_path in (path, index_path):
        with open(os.path.join(storage_dir, stored_path), "rb") as fp:
            assert fp.read() == expected_content
        with open(os.path.join(storage_dir, stored_path + ".meta")) as fp:
            assert json.load(fp) == expected_meta
