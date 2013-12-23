# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import datetime
import os.path
import urlparse
import logging

from warehouse import models
from warehouse.packaging.tables import ReleaseDependencyKind


log = logging.getLogger(__name__)


class Model(models.Model):

    def get_project_count(self):
        query = "SELECT COUNT(*) FROM packages"

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()

    def get_download_count(self):
        query = "SELECT SUM(downloads) FROM release_files"

        with self.engine.connect() as conn:
            return conn.execute(query).scalar()

    def get_recently_updated(self, num=10):
        # We only consider releases made in the last 7 days, otherwise we have
        #   to do a Sequence Scan against the entire table and it takes 5+
        #   seconds to complete. This shouldn't be a big deal as it is highly
        #   unlikely we'll have a week without at least 10 releases.
        query = \
            """ SELECT *
                FROM (
                    SELECT DISTINCT ON (name) name, version, summary, created
                    FROM releases
                    WHERE created >= now() - interval '7 days'
                    ORDER BY name, created DESC
                ) r
                ORDER BY r.created DESC
                LIMIT %(num)s
            """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, num=num)]

    def get_releases_since(self, since):
        query = \
            """ SELECT name, version, created, summary
                FROM releases
                WHERE created > %(since)s
                ORDER BY created DESC
            """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, since=since)]

    def get_changed_since(self, since):
        query = \
            """SELECT name, max(submitted_date) FROM journals
               WHERE submitted_date > %(since)s
               GROUP BY name
               ORDER BY max(submitted_date) DESC
            """

        with self.engine.connect() as conn:
            return [r[0] for r in conn.execute(query, since=since)]

    def all_projects(self):
        query = "SELECT name FROM packages ORDER BY lower(name)"

        with self.engine.connect() as conn:
            return [r["name"] for r in conn.execute(query)]

    def get_top_projects(self, num=None):
        query = \
            """ SELECT name, sum(downloads)
                FROM release_files
                GROUP BY name
                ORDER BY sum(downloads) DESC
            """
        if num:
            query += "LIMIT %(limit)s"

        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(query, limit=num)]

    def get_recent_projects(self, num=10):
        # We only consider projects registered in the last 7 days (see
        # get_recently_updated for reasoning)
        query = \
            """ SELECT
                    p.name, r.version, p.created, r.summary
                FROM releases r, (
                    SELECT packages.name, max_order, packages.created
                    FROM packages
                    JOIN (
                       SELECT name, max(_pypi_ordering) AS max_order
                         FROM releases
                        WHERE created >= now() - interval '7 days'
                        GROUP BY name
                    ) mo ON packages.name = mo.name
                ) p
                WHERE p.name = r.name
                  AND p.max_order = r._pypi_ordering
                  AND p.created >= now() - interval '7 days'
                ORDER BY p.created DESC
                LIMIT %(num)s
            """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, num=num)]

    def get_project(self, name):
        query = \
            """ SELECT name
                FROM packages
                WHERE normalized_name = lower(
                    regexp_replace(%(name)s, '_', '-', 'ig')
                )
            """

        with self.engine.connect() as conn:
            return conn.execute(query, name=name).scalar()

    def get_projects_for_user(self, username):
        query = \
            """ SELECT DISTINCT ON (lower(name)) name, summary
                FROM (
                    SELECT package_name
                    FROM roles
                    WHERE user_name = %(username)s
                ) roles
                INNER JOIN (
                    SELECT name, summary
                    FROM releases
                    ORDER BY _pypi_ordering DESC
                ) releases
                ON (releases.name = roles.package_name)
                ORDER BY lower(name)
            """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, username=username)]

    def get_users_for_project(self, project):
        query = \
            """ SELECT DISTINCT ON (u.username) u.username, u.email
                FROM (
                    SELECT username, email
                    FROM accounts_user
                    LEFT OUTER JOIN accounts_email ON (
                        accounts_email.user_id = accounts_user.id
                    )
                ) u
                INNER JOIN roles ON (u.username = roles.user_name)
                WHERE roles.package_name = %(project)s
            """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, project=project)]

    def get_roles_for_project(self, project):
        query = \
            """ SELECT user_name, role_name
                FROM roles
                WHERE package_name = %(project)s
                ORDER BY role_name, user_name
            """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, project=project)]

    def get_roles_for_user(self, user):
        query = \
            """ SELECT package_name, role_name
                FROM roles
                WHERE user_name = %(user)s
                ORDER BY package_name, role_name
            """

        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, user=user)]

    def get_hosting_mode(self, name):
        query = "SELECT hosting_mode FROM packages WHERE name = %(project)s"

        with self.engine.connect() as conn:
            return conn.execute(query, project=name).scalar()

    def get_release_urls(self, name):
        query = \
            """ SELECT version, home_page, download_url
                FROM releases
                WHERE name = %(project)s
                ORDER BY version DESC
            """

        with self.engine.connect() as conn:
            return {
                r["version"]: (r["home_page"], r["download_url"])
                for r in conn.execute(query, project=name)
            }

    def get_external_urls(self, name):
        query = \
            """ SELECT DISTINCT ON (url) url
                FROM description_urls
                WHERE name = %(project)s
                ORDER BY url
            """

        with self.engine.connect() as conn:
            return [r["url"] for r in conn.execute(query, project=name)]

    def get_file_urls(self, name):
        query = \
            """ SELECT name, filename, python_version, md5_digest
                FROM release_files
                WHERE name = %(project)s
                ORDER BY filename DESC
            """

        with self.engine.connect() as conn:
            results = conn.execute(query, project=name)

            return [
                {
                    "filename": r["filename"],
                    "url": urlparse.urljoin(
                        "/".join([
                            "../../packages",
                            r["python_version"],
                            r["name"][0],
                            r["name"],
                            r["filename"],
                        ]),
                        "#md5={}".format(r["md5_digest"]),
                    ),
                }
                for r in results
            ]

    def get_project_for_filename(self, filename):
        query = "SELECT name FROM release_files WHERE filename = %(filename)s"

        with self.engine.connect() as conn:
            return conn.execute(query, filename=filename).scalar()

    def get_filename_md5(self, filename):
        query = \
            """ SELECT md5_digest
                FROM release_files
                WHERE filename = %(filename)s
            """

        with self.engine.connect() as conn:
            return conn.execute(query, filename=filename).scalar()

    def get_last_serial(self, name=None):
        if name is not None:
            query = "SELECT MAX(id) FROM journals WHERE name = %(name)s"
        else:
            query = "SELECT MAX(id) FROM journals"

        with self.engine.connect() as conn:
            return conn.execute(query, name=name).scalar()

    def get_projects_with_serial(self):
        # return list of dict(name: max id)
        query = "SELECT name, max(id) FROM journals GROUP BY name"

        with self.engine.connect() as conn:
            return dict(r for r in conn.execute(query))

    def get_project_versions(self, project):
        query = \
            """ SELECT version
                FROM releases
                WHERE name = %(project)s
                ORDER BY _pypi_ordering DESC
            """

        with self.engine.connect() as conn:
            return [r["version"] for r in conn.execute(query, project=project)]

    def get_downloads(self, project, version):
        query = \
            """ SELECT
                    name, version, python_version, packagetype, comment_text,
                    filename, md5_digest, downloads, upload_time
                FROM release_files
                WHERE name = %(project)s AND version = %(version)s
                ORDER BY packagetype, python_version, upload_time
            """

        results = []
        with self.engine.connect() as conn:
            for r in conn.execute(query, project=project, version=version):
                result = dict(r)
                result["filepath"] = os.path.join(
                    self.app.config.paths.packages,
                    result["python_version"],
                    result["name"][0],
                    result["name"],
                    result["filename"],
                )
                if not os.path.exists(result["filepath"]):
                    log.error(
                        "%s missing for package %s %s",
                        result["filepath"],
                        result["name"],
                        result["version"])
                    continue
                result["url"] = "/".join([
                    "/packages",
                    result["python_version"],
                    result["name"][0],
                    result["name"],
                    result["filename"],
                ])
                result["size"] = os.path.getsize(result["filepath"])

                if os.path.exists(result["filepath"] + ".asc"):
                    result["pgp_url"] = result["url"] + ".asc"
                else:
                    result["pgp_url"] = None

                results.append(result)

        return results

    def get_release(self, project, version):
        query = \
            """ SELECT
                    name, version, author, author_email, maintainer,
                    maintainer_email, home_page, license, summary, description,
                    keywords, platform, download_url, created
                FROM releases
                WHERE name = %(project)s AND version = %(version)s
                ORDER BY _pypi_ordering DESC
                LIMIT 1
            """

        with self.engine.connect() as conn:
            result = [
                dict(r)
                for r in conn.execute(query, project=project, version=version)
            ][0]

        # Load dependency information
        query = \
            """ SELECT name, version, kind, specifier
                FROM release_dependencies
                WHERE name = %(project)s AND version = %(version)s
                ORDER BY kind, specifier
            """

        dependency_data = {}
        with self.engine.connect() as conn:
            for dependency in conn.execute(
                    query,
                    project=project,
                    version=version):
                kind = ReleaseDependencyKind(dependency["kind"])

                if kind in {
                        ReleaseDependencyKind.requires_dist,
                        ReleaseDependencyKind.provides_dist,
                        ReleaseDependencyKind.obsoletes_dist}:
                    value = dependency_data.setdefault(kind.name, [])
                    value.append(dependency["specifier"])

                if kind is ReleaseDependencyKind.project_url:
                    value = dependency_data.setdefault(kind.name, {})
                    value.update(dict([dependency["specifier"].split(",", 1)]))
        result.update(dependency_data)

        return result

    def get_releases(self, project):
        # Get the release data
        query = \
            """ SELECT
                    name, version, author, author_email, maintainer,
                    maintainer_email, home_page, license, summary, keywords,
                    platform, download_url, created
                FROM releases
                WHERE name = %(project)s
                ORDER BY _pypi_ordering DESC
            """

        with self.engine.connect() as conn:
            results = [dict(r) for r in conn.execute(query, project=project)]

        return results

    def get_full_latest_releases(self):
        query = \
            """ SELECT DISTINCT ON (name)
                    name, version, author, author_email, maintainer,
                    maintainer_email, home_page, license, summary, description,
                    keywords, platform, download_url, created
                FROM releases
                ORDER BY name, _pypi_ordering DESC
            """

        with self.engine.connect() as conn:
            results = [dict(r) for r in conn.execute(query)]

        return results

    def get_download_counts(self, project):
        def _make_key(precision, datetime, key):
            return "downloads:{}:{}:{}".format(
                precision[0],
                datetime.strftime(precision[1]),
                key,
            )

        precisions = [
            ("hour", "%y-%m-%d-%H"),
            ("daily", "%y-%m-%d"),
        ]

        # Get the current utc time
        current = datetime.datetime.utcnow()

        # Get the download count for the last 24 hours (roughly)
        keys = [
            _make_key(
                precisions[0],
                current - datetime.timedelta(hours=x),
                project,
            )
            for x in range(25)
        ]
        last_1 = sum(
            [int(x) for x in self.redis.mget(*keys) if x is not None]
        )

        # Get the download count for the last 7 days (roughly)
        keys = [
            _make_key(
                precisions[1],
                current - datetime.timedelta(days=x),
                project,
            )
            for x in range(8)
        ]
        last_7 = sum(
            [int(x) for x in self.redis.mget(*keys) if x is not None]
        )

        # Get the download count for the last month (roughly)
        keys = [
            _make_key(
                precisions[1],
                current - datetime.timedelta(days=x),
                project,
            )
            for x in range(31)
        ]
        last_30 = sum(
            [int(x) for x in self.redis.mget(*keys) if x is not None]
        )

        return {
            "last_day": last_1,
            "last_week": last_7,
            "last_month": last_30,
        }

    def get_classifiers(self, project, version):
        query = \
            """ SELECT classifier
                FROM release_classifiers
                INNER JOIN trove_classifiers ON (
                    release_classifiers.trove_id = trove_classifiers.id
                )
                WHERE name = %(project)s AND version = %(version)s
                ORDER BY classifier
            """

        with self.engine.connect() as conn:
            return [
                r["classifier"]
                for r in conn.execute(query, project=project, version=version)
            ]

    def get_classifier_ids(self, classifiers):
        placeholders = ', '.join(['%s'] * len(classifiers))
        query = \
            """SELECT classifier, id
                 FROM trove_classifiers
                WHERE classifier IN (%s)
            """ % placeholders

        with self.engine.connect() as conn:
            return dict((r['classifier'], r['id'])
                        for r in conn.execute(query, *classifiers))

    def search_by_classifier(self, selected_classifiers):
        # Note: selected_classifiers is a list of ids from trove_classifiers
        if not selected_classifiers:
            return []

        # generate trove id -> level mapping
        trove = {}
        query = "SELECT * FROM trove_classifiers"
        with self.engine.connect() as conn:
            for id, classifier, l2, l3, l4, l5 in conn.execute(query):
                if id == l2:
                    trove[id] = 2
                elif id == l3:
                    trove[id] = 3
                elif id == l4:
                    trove[id] = 4
                else:
                    trove[id] = 5

        # compute a statement to produce all packages selected
        query = "SELECT name, version FROM releases"
        for c in selected_classifiers:
            level = trove[c]
            query = \
                """ SELECT DISTINCT a.name, a.version
                    FROM (%s) a, release_classifiers rc, trove_classifiers t
                    WHERE a.name=rc.name
                    AND a.version=rc.version
                    AND rc.trove_id=t.id
                    AND t.l%d=%d
                """ % (query, level, c)

        releases = []
        with self.engine.connect() as conn:
            for name, version in conn.execute(query):
                releases.append((name.decode('utf-8'), version))

        return releases

    def get_documentation_url(self, project):
        path_parts = [
            self.app.config.paths.documentation,
            project,
            "index.html",
        ]
        if os.path.exists(os.path.join(*path_parts)):
            return urlparse.urljoin(
                self.app.config.urls.documentation,
                project
            ) + "/"

    def get_bugtrack_url(self, project):
        query = "SELECT bugtrack_url FROM packages WHERE name = %(project)s"

        with self.engine.connect() as conn:
            return conn.execute(query, project=project).scalar()

    #
    # Mirroring support
    #
    def get_changelog(self, since):
        query = '''SELECT name, version, submitted_date, action, id
            FROM journals
            WHERE journals.submitted_date > %(since)s
            ORDER BY submitted_date DESC
        '''
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, since=since)]

    def get_last_changelog_serial(self):
        with self.engine.connect() as conn:
            return conn.execute('SELECT max(id) FROM journals').scalar()

    def get_changelog_serial(self, since):
        query = '''SELECT name, version, submitted_date, action, id
            FROM journals
            WHERE journals.id > %(since)s
            ORDER BY submitted_date DESC
        '''
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query, since=since)]
