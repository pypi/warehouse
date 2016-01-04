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

import datetime
import functools

from elasticsearch_dsl import Q
from pyramid.view import view_config
from pyramid_rpc.xmlrpc import exception_view as _exception_view, xmlrpc_method
from sqlalchemy import func, select
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.csrf import csrf_exempt
from warehouse.packaging.interfaces import IDownloadStatService
from warehouse.packaging.models import (
    Role, Project, Release, File, JournalEntry, release_classifiers,
)


pypi_xmlrpc = functools.partial(xmlrpc_method, endpoint="pypi")


@view_config(
    route_name="pypi",
    context=Exception,
    renderer="xmlrpc",
    decorator=[csrf_exempt],
)
def exception_view(exc, request):
    return _exception_view(exc, request)


@pypi_xmlrpc(method="search")
def search(request, spec, operator="and"):
    if operator not in {"and", "or"}:
        raise ValueError("Invalid operator, must be one of 'and' or 'or'.")

    # Remove any invalid spec fields
    spec = {
        k: [v] if isinstance(v, str) else v
        for k, v in spec.items()
        if v and k in {
            "name", "version", "author", "author_email", "maintainer",
            "maintainer_email", "home_page", "license", "summary",
            "description", "keywords", "platform", "download_url",
        }
    }

    queries = []
    for field, value in sorted(spec.items()):
        q = None
        for item in value:
            if q is None:
                q = Q("match", **{field: item})
            else:
                q |= Q("match", **{field: item})
        queries.append(q)

    if operator == "and":
        query = request.es.query("bool", must=queries)
    else:
        query = request.es.query("bool", should=queries)

    results = query[:1000].execute()

    return [
        {"name": r.name, "summary": r.summary, "version": v}
        for r in results
        for v in r.version
        if v in spec.get("version", [v])
    ]


@pypi_xmlrpc(method="list_packages")
def list_packages(request):
    names = request.db.query(Project.name).order_by(Project.name).all()
    return [n[0] for n in names]


@pypi_xmlrpc(method="list_packages_with_serial")
def list_packages_with_serial(request):
    serials = (
        request.db.query(JournalEntry.name, func.max(JournalEntry.id))
                  .join(Project, JournalEntry.name == Project.name)
                  .group_by(JournalEntry.name)
    )
    return dict((serial[0], serial[1]) for serial in serials)


@pypi_xmlrpc(method="package_hosting_mode")
def package_hosting_mode(request, package_name):
    try:
        project = (
            request.db.query(Project)
                      .filter(Project.normalized_name ==
                              func.normalize_pep426_name(package_name))
                      .one()
        )
    except NoResultFound:
        return None
    else:
        return project.hosting_mode


@pypi_xmlrpc(method="user_packages")
def user_packages(request, username):
    roles = (
        request.db.query(Role)
                  .join(User, Project)
                  .filter(User.username == username)
                  .order_by(Role.role_name.desc(), Project.name)
                  .all()
    )
    return [(r.role_name, r.project.name) for r in roles]


@pypi_xmlrpc(method="top_packages")
def top_packages(request, num=None):
    fdownloads = func.sum(File.downloads).label("downloads")

    downloads = (
        request.db.query(File.name, fdownloads)
                  .group_by(File.name)
                  .order_by(fdownloads.desc())
    )

    if num is not None:
        downloads = downloads.limit(num)

    return [(d[0], d[1]) for d in downloads.all()]


@pypi_xmlrpc(method="package_releases")
def package_releases(request, package_name, show_hidden=False):
    # This used to support the show_hidden parameter to determine if it should
    # show hidden releases or not. However, Warehouse doesn't support the
    # concept of hidden releases, so it is just no-opd now and left here for
    # compatibility's sake.
    versions = (
        request.db.query(Release.version)
                  .join(Project)
                  .filter(Project.normalized_name ==
                          func.normalize_pep426_name(package_name))
                  .order_by(Release._pypi_ordering)
                  .all()
    )
    return [v[0] for v in versions]


@pypi_xmlrpc(method="release_data")
def release_data(request, package_name, version):
    try:
        release = (
            request.db.query(Release)
                      .join(Project)
                      .filter((Project.normalized_name ==
                               func.normalize_pep426_name(package_name)) &
                              (Release.version == version))
                      .one()
        )
    except NoResultFound:
        return {}

    stats_svc = request.find_service(IDownloadStatService)

    return {
        "name": release.project.name,
        "version": release.version,
        "stable_version": release.project.stable_version,
        "bugtrack_url": release.project.bugtrack_url,
        "package_url": request.route_url(
            "packaging.project",
            name=release.project.name,
        ),
        "release_url": request.route_url(
            "packaging.release",
            name=release.project.name,
            version=release.version,
        ),
        "docs_url": release.project.documentation_url,
        "home_page": release.home_page,
        "download_url": release.download_url,
        "project_url": list(release.project_urls),
        "author": release.author,
        "author_email": release.author_email,
        "maintainer": release.maintainer,
        "maintainer_email": release.maintainer_email,
        "summary": release.summary,
        "description": release.description,
        "license": release.license,
        "keywords": release.keywords,
        "platform": release.platform,
        "classifiers": list(release.classifiers),
        "requires": list(release.requires),
        "requires_dist": list(release.requires_dist),
        "provides": list(release.provides),
        "provides_dist": list(release.provides_dist),
        "obsoletes": list(release.obsoletes),
        "obsoletes_dist": list(release.obsoletes_dist),
        "requires_python": release.requires_python,
        "requires_external": list(release.requires_external),
        "_pypi_ordering": release._pypi_ordering,
        "_pypi_hidden": release._pypi_hidden,
        "downloads": {
            "last_day": stats_svc.get_daily_stats(release.project.name),
            "last_week": stats_svc.get_weekly_stats(release.project.name),
            "last_month": stats_svc.get_monthly_stats(release.project.name),
        },
    }


@pypi_xmlrpc(method="release_urls")
def release_urls(request, package_name, version):
    files = (
        request.db.query(File)
                  .join(Release, Project)
                  .filter((Project.normalized_name ==
                           func.normalize_pep426_name(package_name)) &
                          (Release.version == version))
                  .all()
    )

    return [
        {
            "filename": f.filename,
            "packagetype": f.packagetype,
            "python_version": f.python_version,
            "size": f.size,
            "md5_digest": f.md5_digest,
            "digests": {
                "md5": f.md5_digest,
                "sha256": f.sha256_digest,
            },
            "has_sig": f.has_signature,
            "upload_time": f.upload_time,
            "comment_text": f.comment_text,
            "downloads": f.downloads,
            "url": request.route_url("packaging.file", path=f.path),
        }
        for f in files
    ]


@pypi_xmlrpc(method="package_roles")
def package_roles(request, package_name):
    roles = (
        request.db.query(Role)
                  .join(User, Project)
                  .filter(Project.normalized_name ==
                          func.normalize_pep426_name(package_name))
                  .order_by(Role.role_name.desc(), User.username)
                  .all()
    )
    return [(r.role_name, r.user.username) for r in roles]


@pypi_xmlrpc(method="changelog_last_serial")
def changelog_last_serial(request):
    return request.db.query(func.max(JournalEntry.id)).scalar()


@pypi_xmlrpc(method="changelog_since_serial")
def changelog_since_serial(request, serial):
    entries = (
        request.db.query(JournalEntry)
                  .filter(JournalEntry.id > serial)
                  .order_by(JournalEntry.id)
                  .all()
    )

    return [
        (
            e.name,
            e.version,
            int(
                e.submitted_date
                 .replace(tzinfo=datetime.timezone.utc)
                 .timestamp()
            ),
            e.action,
            e.id,
        )
        for e in entries
    ]


@pypi_xmlrpc(method="changelog")
def changelog(request, since, with_ids=False):
    since = datetime.datetime.utcfromtimestamp(since)
    entries = (
        request.db.query(JournalEntry)
                  .filter(JournalEntry.submitted_date > since)
                  .order_by(JournalEntry.id)
                  .all()
    )

    results = (
        (
            e.name,
            e.version,
            int(
                e.submitted_date
                 .replace(tzinfo=datetime.timezone.utc)
                 .timestamp()
            ),
            e.action,
            e.id,
        )
        for e in entries
    )

    if with_ids:
        return list(results)
    else:
        return [r[:-1] for r in results]


@pypi_xmlrpc(method="browse")
def browse(request, classifiers):
    classifiers_q = (
        request.db.query(Classifier)
               .filter(Classifier.classifier.in_(classifiers))
               .subquery()
    )

    release_classifiers_q = (
        select([release_classifiers])
        .where(release_classifiers.c.trove_id == classifiers_q.c.id)
        .alias("rc")
    )

    releases = (
        request.db.query(Release.name, Release.version)
                  .join(release_classifiers_q,
                        (Release.name == release_classifiers_q.c.name) &
                        (Release.version == release_classifiers_q.c.version))
                  .group_by(Release.name, Release.version)
                  .having(func.count() == len(classifiers))
                  .order_by(Release.name, Release.version)
                  .all()
    )

    return [(r.name, r.version) for r in releases]
