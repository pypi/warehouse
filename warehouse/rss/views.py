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

from datetime import timedelta
from email.utils import getaddresses

from pyramid.view import view_config
from sqlalchemy.orm import joinedload

from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Project, Release


def _format_author(release):
    """
    Format release author suitably for inclusion in an RSS feed.

    Release author names and emails are hard to match robustly, mainly
    because there may be multiple in both, and especially the names may
    contain pretty much anything. So stick with just the emails with some
    rudimentary sanity checks.

    Even though the spec says "the email address" and thus assumes a single
    author, we let multiple pass, comma separated.

    http://www.rssboard.org/rss-specification#ltauthorgtSubelementOfLtitemgt
    """
    author_emails = []
    for _, author_email in getaddresses([release.author_email or ""]):
        if "@" not in author_email:
            # Require all valid looking
            return None
        author_emails.append(author_email)

    return ", ".join(author_emails)


@view_config(
    route_name="rss.updates",
    renderer="rss/updates.xml",
    decorator=[
        origin_cache(
            timedelta(days=1).total_seconds(),
            stale_while_revalidate=timedelta(days=1).total_seconds(),
            stale_if_error=timedelta(days=5).total_seconds(),
            keys=["all-projects"],
        )
    ],
)
def rss_updates(request):
    request.response.content_type = "text/xml"

    latest_releases = (
        request.db.query(Release)
        .options(joinedload(Release.project))
        .order_by(Release.created.desc())
        .limit(100)
        .all()
    )
    release_authors = [_format_author(release) for release in latest_releases]

    return {"latest_releases": tuple(zip(latest_releases, release_authors))}


@view_config(
    route_name="rss.packages",
    renderer="rss/packages.xml",
    decorator=[
        origin_cache(
            timedelta(days=1).total_seconds(),
            stale_while_revalidate=timedelta(days=1).total_seconds(),
            stale_if_error=timedelta(days=5).total_seconds(),
            keys=["all-projects"],
        )
    ],
)
def rss_packages(request):
    request.response.content_type = "text/xml"

    newest_projects = (
        request.db.query(Project)
        .options(joinedload(Project.releases, innerjoin=True))
        .order_by(Project.created.desc().nulls_last())
        .limit(40)
        .all()
    )
    project_authors = [
        _format_author(project.releases[0]) for project in newest_projects
    ]

    return {"newest_projects": tuple(zip(newest_projects, project_authors))}


@view_config(
    route_name="rss.project.releases",
    context=Project,
    renderer="rss/project_releases.xml",
    decorator=[
        origin_cache(
            timedelta(days=1).total_seconds(),
            stale_if_error=timedelta(days=5).total_seconds(),
        )
    ],
)
def rss_project_releases(project, request):
    request.response.content_type = "text/xml"

    latest_releases = (
        request.db.query(Release)
        .filter(Release.project == project)
        .order_by(Release.created.desc())
        .limit(40)
        .all()
    )
    release_authors = [_format_author(release) for release in latest_releases]

    return {
        "project": project,
        "latest_releases": tuple(zip(latest_releases, release_authors)),
    }
