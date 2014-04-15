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

import json
import time

from flask import (
    Blueprint, current_app as app, request, url_for, render_template
)
from werkzeug.utils import redirect
from werkzeug.exceptions import NotFound, BadRequest

from warehouse import fastly
from warehouse.legacy import xmlrpc
from warehouse.utils import (
    cache, cors, is_valid_json_callback_name
)

blueprint = Blueprint('warehouse.legacy.pypi', __name__)


@blueprint.route('/pypi', methods=['GET', 'POST'])
def pypi():
    # if the MIME type of the request is XML then we go into XML-RPC mode
    if request.headers.get('Content-Type') == 'text/xml':
        return xmlrpc.handle_request(app, request)

    # no XML-RPC and no :action means we render the index, or at least we
    # redirect to where it moved to
    return redirect(
        url_for("warehouse.views.index"),
        code=301,
    )


@blueprint.route('/daytime')
def daytime():
    response = time.strftime("%Y%m%dT%H:%M:%S\n", time.gmtime(time.time()))
    return app.response_class(response, mimetype="text/plain")


@blueprint.route("/pypi/<project_name>/json")
@cors
@cache(browser=1, varnish=120)
@fastly.projects(project_name="project")
def project_json(project_name):
    # fail early if callback is invalid
    callback = request.args.get('callback')
    if callback:
        if not is_valid_json_callback_name(callback):
            raise BadRequest('invalid JSONP callback name')

    # Get the real project name for this project
    project = app.db.packaging.get_project(project_name)

    if project is None:
        raise NotFound("{} does not exist".format(project_name))

    # we're looking for the latest version
    versions = app.db.packaging.get_project_versions(project)
    if not versions:
        raise NotFound("{} has no releases".format(project))
    version = versions[0]

    rpc = xmlrpc.Interface(app, request)

    d = dict(
        info=rpc.release_data(project, version),
        urls=rpc.release_urls(project, version),
    )
    for url in d['urls']:
        url['upload_time'] = url['upload_time'].strftime('%Y-%m-%dT%H:%M:%S')

    data = json.dumps(d, sort_keys=True)

    # write the JSONP extra crap if necessary
    if callback:
        data = '/**/ %s(%s);' % (callback, data)

    response = app.response_class(
        data, mimetype="application/json"
    )
    response.headers['Content-Disposition'] = 'inline'
    return response


@cache(browser=1, varnish=120)
@fastly.rss
def rss():
    """Dump the last N days' updates as an RSS feed.
    """
    releases = app.db.packaging.get_recently_updated(num=40)
    for release in releases:
        values = dict(project_name=release['name'], version=release['version'])
        url = url_for(
            'warehouse.packaging.views.project_detail',
            _external=True, **values
        )
        release.update(dict(url=url))

    response = app.response_class(
        render_template(
            "legacy/rss.xml",
            description='package updates',
            releases=releases,
            site=app.warehouse_config.site,
        ),
        mimetype='text/xml; charset=utf-8'
    )
    # TODO: throw in a last-modified header too?
    return response


@cache(browser=1, varnish=120)
@fastly.rss
def packages_rss():
    """Dump the last N days' new projects as an RSS feed.
    """
    releases = app.db.packaging.get_recent_projects(num=40)
    for release in releases:
        values = dict(project_name=release['name'])
        url = url_for(
            'warehouse.packaging.views.project_detail',
            _external=True, **values
        )
        release.update(dict(url=url))

    response = app.response_class(
        render_template(
            "legacy/rss.xml",
            description='new projects',
            releases=releases,
            site=app.warehouse_config.site,
        ),
        mimetype='text/xml; charset=utf-8'
    )
    # TODO: throw in a last-modified header too?
    return response
