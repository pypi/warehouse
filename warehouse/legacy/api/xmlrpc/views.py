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

import collections.abc
import datetime
import functools
import xmlrpc.client
import xmlrpc.server

from elasticsearch_dsl import Q
from packaging.utils import canonicalize_name
from pyramid.view import view_config
from pyramid_rpc.xmlrpc import (
    exception_view as _exception_view, xmlrpc_method as _xmlrpc_method
)
from sqlalchemy import func, orm, select
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.packaging.models import (
    Role, Project, Release, File, JournalEntry, release_classifiers,
)
from warehouse.search.queries import SEARCH_BOOSTS


_MAX_MULTICALLS = 20


def xmlrpc_method(**kwargs):
    """
    Support multiple endpoints serving the same views by chaining calls to
    xmlrpc_method
    """
    # Add some default arguments
    kwargs.update(require_csrf=False, require_methods=["POST"])

    def decorator(f):
        rpc2 = _xmlrpc_method(endpoint='RPC2', **kwargs)
        pypi = _xmlrpc_method(endpoint='pypi', **kwargs)
        pypi_slash = _xmlrpc_method(endpoint='pypi_slash', **kwargs)
        return rpc2(pypi_slash(pypi(f)))

    return decorator


xmlrpc_cache_by_project = functools.partial(
    xmlrpc_method,
    xmlrpc_cache=True,
    xmlrpc_cache_expires=24 * 60 * 60,  # 24 hours
    xmlrpc_cache_tag='project/%s',
    xmlrpc_cache_arg_index=0,
    xmlrpc_cache_tag_processor=canonicalize_name,
)


class XMLRPCWrappedError(xmlrpc.server.Fault):

    def __init__(self, exc):
        self.faultCode = -32500
        self.wrapped_exception = exc

    @property
    def faultString(self):  # noqa
        return "{exc.__class__.__name__}: {exc}".format(
            exc=self.wrapped_exception,
        )


@view_config(route_name="pypi", context=Exception, renderer="xmlrpc")
def exception_view(exc, request):
    return _exception_view(exc, request)


@xmlrpc_method(method="search")
def search(request, spec, operator="and"):
    if not isinstance(spec, collections.abc.Mapping):
        raise XMLRPCWrappedError(
            TypeError("Invalid spec, must be a mapping/dictionary.")
        )

    if operator not in {"and", "or"}:
        raise XMLRPCWrappedError(
            ValueError("Invalid operator, must be one of 'and' or 'or'.")
        )

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
            kw = {"query": item}
            if field in SEARCH_BOOSTS:
                kw["boost"] = SEARCH_BOOSTS[field]
            if q is None:
                q = Q("match", **{field: kw})
            else:
                q |= Q("match", **{field: kw})
        queries.append(q)

    if operator == "and":
        query = request.es.query("bool", must=queries)
    else:
        query = request.es.query("bool", should=queries)

    results = query[:100].execute()

    request.registry.datadog.histogram('warehouse.xmlrpc.search.results',
                                       len(results))

    if "version" in spec.keys():
        return [
            {
                "name": r.name,
                "summary": r.summary,
                "version": v,
                "_pypi_ordering": False
            }
            for r in results
            for v in r.version
            if v in spec.get("version", [v])
        ]
    return [
        {
            "name": r.name,
            "summary": r.summary,
            "version": r.latest_version,
            "_pypi_ordering": False
        }
        for r in results
    ]


@xmlrpc_method(method="list_packages")
def list_packages(request):
    names = request.db.query(Project.name).order_by(Project.name).all()
    return [n[0] for n in names]


@xmlrpc_method(method="list_packages_with_serial")
def list_packages_with_serial(request):
    serials = request.db.query(Project.name, Project.last_serial).all()
    return dict((serial[0], serial[1]) for serial in serials)


@xmlrpc_method(method="package_hosting_mode")
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


@xmlrpc_method(method="user_packages")
def user_packages(request, username):
    roles = (
        request.db.query(Role)
                  .join(User, Project)
                  .filter(User.username == username)
                  .order_by(Role.role_name.desc(), Project.name)
                  .all()
    )
    return [(r.role_name, r.project.name) for r in roles]


@xmlrpc_method(method="top_packages")
def top_packages(request, num=None):
    raise XMLRPCWrappedError(
        RuntimeError("This API has been removed. Please Use BigQuery instead.")
    )


@xmlrpc_cache_by_project(method="package_releases")
def package_releases(request, package_name, show_hidden=False):
    try:
        project = (
            request.db.query(Project)
                      .filter(Project.normalized_name ==
                              func.normalize_pep426_name(package_name))
                      .one()
        )
    except NoResultFound:
        return []

    # This used to support the show_hidden parameter to determine if it should
    # show hidden releases or not. However, Warehouse doesn't support the
    # concept of hidden releases, so this parameter controls if the latest
    # version or all_versions are returned.
    if show_hidden:
        return [v.version for v in project.all_versions]
    else:
        latest_version = project.latest_version
        if latest_version is None:
            return []
        return [latest_version.version]


@xmlrpc_method(method="package_data")
def package_data(request, package_name, version):
    settings = request.registry.settings
    domain = settings.get("warehouse.domain", request.domain)
    raise XMLRPCWrappedError(
        RuntimeError(
            ("This API has been deprecated. Use "
             f"https://{domain}/{package_name}/{version}/json "
             "instead. The XMLRPC method release_data can be used in the "
             "interim, but will be deprecated in the future.")
        )
    )


@xmlrpc_cache_by_project(method="release_data")
def release_data(request, package_name, version):
    try:
        release = (
            request.db.query(Release)
                      .options(orm.undefer("description"))
                      .join(Project)
                      .filter((Project.normalized_name ==
                               func.normalize_pep426_name(package_name)) &
                              (Release.version == version))
                      .one()
        )
    except NoResultFound:
        return {}

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
            "last_day": -1,
            "last_week": -1,
            "last_month": -1,
        },
        "cheesecake_code_kwalitee_id": None,
        "cheesecake_documentation_id": None,
        "cheesecake_installability_id": None,
    }


@xmlrpc_method(method="package_urls")
def package_urls(request, package_name, version):
    settings = request.registry.settings
    domain = settings.get("warehouse.domain", request.domain)
    raise XMLRPCWrappedError(
        RuntimeError(
            ("This API has been deprecated. Use "
             f"https://{domain}/{package_name}/{version}/json "
             "instead. The XMLRPC method release_urls can be used in the "
             "interim, but will be deprecated in the future.")
        )
    )


@xmlrpc_cache_by_project(method="release_urls")
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
            "sha256_digest": f.sha256_digest,
            "digests": {
                "md5": f.md5_digest,
                "sha256": f.sha256_digest,
            },
            "has_sig": f.has_signature,
            "upload_time": f.upload_time.isoformat() + "Z",
            "comment_text": f.comment_text,
            # TODO: Remove this once we've had a long enough time with it
            #       here to consider it no longer in use.
            "downloads": -1,
            "path": f.path,
            "url": request.route_url("packaging.file", path=f.path),
        }
        for f in files
    ]


@xmlrpc_cache_by_project(method="package_roles")
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


@xmlrpc_method(method="changelog_last_serial")
def changelog_last_serial(request):
    return request.db.query(func.max(JournalEntry.id)).scalar()


@xmlrpc_method(method="changelog_since_serial")
def changelog_since_serial(request, serial):
    entries = (
        request.db.query(JournalEntry)
                  .filter(JournalEntry.id > serial)
                  .order_by(JournalEntry.id)
                  .limit(50000)
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


@xmlrpc_method(method="changelog")
def changelog(request, since, with_ids=False):
    since = datetime.datetime.utcfromtimestamp(since)
    entries = (
        request.db.query(JournalEntry)
                  .filter(JournalEntry.submitted_date > since)
                  .order_by(JournalEntry.id)
                  .limit(50000)
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


@xmlrpc_method(method="browse")
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


@xmlrpc_method(method='system.multicall')
def multicall(request, args):
    raise XMLRPCWrappedError(
        ValueError(
            'MultiCall requests have been deprecated, use individual '
            'requests instead.'
        )
    )
