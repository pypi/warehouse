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

from pyramid_rpc.xmlrpc import xmlrpc_method
from sqlalchemy import func, select
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.packaging.models import (
    Role, Project, Release, File, JournalEntry, release_classifiers,
)


pypi_xmlrpc = functools.partial(xmlrpc_method, endpoint="pypi")


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
    # compatability sake.
    versions = (
        request.db.query(Release.version)
                  .join(Project)
                  .filter(Project.normalized_name ==
                          func.normalize_pep426_name(package_name))
                  .order_by(Release._pypi_ordering)
                  .all()
    )
    return [v[0] for v in versions]


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
def changelog(request, since):
    since = datetime.datetime.utcfromtimestamp(since)
    entries = (
        request.db.query(JournalEntry)
                  .filter(JournalEntry.submitted_date > since)
                  .order_by(JournalEntry.submitted_date)
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
