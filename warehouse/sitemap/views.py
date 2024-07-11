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

import collections
import datetime
import itertools

from pyramid.view import view_config
from sqlalchemy import func, or_

from warehouse.accounts.models import User
from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Project

AGE_BEFORE_INDEX = datetime.timedelta(days=14)
SITEMAP_MAXSIZE = 50000


Bucket = collections.namedtuple("Bucket", ["name", "modified"])


@view_config(
    route_name="index.sitemap.xml",
    renderer="sitemap/index.xml",
    decorator=[
        cache_control(1 * 60 * 60),  # 1 hour
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=6 * 60 * 60,  # 6 hours
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
            keys=["all-projects"],
        ),
    ],
)
def sitemap_index(request):
    request.response.content_type = "text/xml"

    # We have > 50,000 URLs on PyPI and a single sitemap file can only support
    # a maximum of 50,000 URLs. We need to split our URLs up into multiple
    # files so we need to stick all of our URLs into buckets, in addition we
    # want our buckets to remain stable so that an URL won't change what bucket
    # it is in just because another URL is added or removed. Finally we also
    # want to minimize the number of buckets we have to reduce the number of
    # HTTP requests on top of the fact that there is also a 50,000 limit of
    # buckets in these scheme before we need to nest buckets. In order to
    # satisfy these requirements we will take the URL and use a SHA512 hash to
    # pseudo-randomly distribute our URLs amongst many buckets, but we'll only
    # take the first letter of the hash to serve as our bucket, and if at some
    # point in the future we need more buckets we can take the first two
    # characters of the hash instead of just the first. Since the hash is a
    # property of the URL what bucket an URL goes into won't be influenced by
    # what other URLs exist in the system.
    projects = (
        request.db.query(
            Project.sitemap_bucket, func.max(Project.created).label("modified")
        )
        .filter(
            Project.created < datetime.datetime.now(datetime.UTC) - AGE_BEFORE_INDEX
        )
        .group_by(Project.sitemap_bucket)
        .all()
    )
    users = (
        request.db.query(
            User.sitemap_bucket, func.max(User.date_joined).label("modified")
        )
        .filter(
            or_(
                User.date_joined
                < datetime.datetime.now(datetime.UTC) - AGE_BEFORE_INDEX,
                User.date_joined.is_(None),
            )
        )
        .group_by(User.sitemap_bucket)
        .all()
    )
    buckets = {}
    for b in itertools.chain(projects, users):
        current = buckets.setdefault(b.sitemap_bucket, b.modified)
        if current is None or (b.modified is not None and b.modified > current):
            buckets[b.sitemap_bucket] = b.modified
    buckets = [Bucket(name=k, modified=v) for k, v in buckets.items()]
    buckets.sort(key=lambda x: x.name)

    return {"buckets": buckets}


@view_config(
    route_name="bucket.sitemap.xml",
    renderer="sitemap/bucket.xml",
    decorator=[
        cache_control(1 * 60 * 60),  # 1 hour
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=6 * 60 * 60,  # 6 hours
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
            keys=["all-projects"],
        ),
    ],
)
def sitemap_bucket(request):
    request.response.content_type = "text/xml"

    bucket = request.matchdict["bucket"]

    projects = (
        request.db.query(Project.normalized_name)
        .filter(
            Project.created < datetime.datetime.now(datetime.UTC) - AGE_BEFORE_INDEX
        )
        .filter(Project.sitemap_bucket == bucket)
        .all()
    )
    users = (
        request.db.query(User.username)
        .filter(User.sitemap_bucket == bucket)
        .filter(
            or_(
                User.date_joined
                < datetime.datetime.now(datetime.UTC) - AGE_BEFORE_INDEX,
                User.date_joined.is_(None),
            )
        )
        .all()
    )

    urls = [
        request.route_url("packaging.project", name=project.normalized_name)
        for project in projects
    ]
    urls += [
        request.route_url("accounts.profile", username=user.username) for user in users
    ]

    # If the length of our bucket name isn't enough to ensure that all of our
    # buckets have less than our maximum number of URLs then we want to error
    # out so that we can adjust our bucket size to spread the URLs out over
    # more buckets.
    if len(urls) > SITEMAP_MAXSIZE:
        raise ValueError(
            "Too many URLs in the sitemap for bucket: {!r}.".format(
                request.matchdict["bucket"]
            )
        )

    return {"urls": sorted(urls)}
