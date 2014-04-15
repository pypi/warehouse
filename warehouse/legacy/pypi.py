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

from flask import Blueprint, current_app, request, render_template, url_for
from werkzeug.utils import redirect
from werkzeug.exceptions import NotFound, BadRequest

from warehouse import fastly
from warehouse.http import Response
from warehouse.legacy import xmlrpc
from warehouse.utils import cache, cors, is_valid_json_callback_name


blueprint = Blueprint("warehouse.legacy.pypi", __name__)


_action_methods = {}


def register(name):
    """Register a handler for a legacy :action style dispatch.

    Most of the dispatch in legacy PyPI was implemented using a :action
    parameter in the GET or POST arguments.

    This doesn't actually decorate the function or alter it in any way, it
    simply registers it with the legacy routing mapping.
    """
    if name in _action_methods:
        raise KeyError('Attempt to re-register name %r' % (name, ))

    def deco(fn):
        _action_methods[name] = fn
        return fn
    return deco


@blueprint.route("/pypi", methods=["GET", "POST"])
def pypi():
    # if the MIME type of the request is XML then we go into XML-RPC mode
    if request.headers.get('Content-Type') == 'text/xml':
        return xmlrpc.handle_request(current_app, request)

    # check for the legacy :action-style dispatch
    action = request.args.get(':action')
    if action in _action_methods:
        return _action_methods[action]()

    # no XML-RPC and no :action means we render the index, or at least we
    # redirect to where it moved to
    return redirect(url_for("warehouse.views.index"), code=301)


@blueprint.route("/daytime", methods=["GET"])
def daytime():
    response = time.strftime("%Y%m%dT%H:%M:%S\n", time.gmtime(time.time()))
    return Response(response, mimetype="text/plain")


@blueprint.route("/pypi/<project_name>/json", methods=["GET"])
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
    project = current_app.db.packaging.get_project(project_name)

    if project is None:
        raise NotFound("{} does not exist".format(project_name))

    # we're looking for the latest version
    versions = current_app.db.packaging.get_project_versions(project)
    if not versions:
        raise NotFound("{} has no releases".format(project))
    version = versions[0]

    rpc = xmlrpc.Interface(current_app, request)

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

    response = Response(data, mimetype="application/json")
    response.headers['Content-Disposition'] = 'inline'
    return response


@register('rss')
@cache(browser=1, varnish=120)
@fastly.rss
def rss():
    """Dump the last N days' updates as an RSS feed.
    """
    releases = current_app.db.packaging.get_recently_updated(num=40)
    for release in releases:
        url = url_for(
            request,
            'warehouse.packaging.views.project_detail',
            project_name=release['name'],
            version=release['version'],
            _force_external=True,
        )
        release.update(dict(url=url))

    return current_app.response_class(
        render_template(
            "legacy/rss.xml",
            description='package updates',
            releases=releases,
            site=current_app.config["site"],
        ),
        mimetype="text/xml",
    )


@register('packages_rss')
@cache(browser=1, varnish=120)
@fastly.rss
def packages_rss():
    """Dump the last N days' new projects as an RSS feed.
    """
    releases = current_app.db.packaging.get_recent_projects(num=40)
    for release in releases:
        url = url_for(
            'warehouse.packaging.views.project_detail',
            project_name=release['name'],
            _external=True,
        )
        release.update(dict(url=url))

    return current_app.response_class(
        render_template(
            "legacy/rss.xml",
            description='new projects',
            releases=releases,
            site=current_app.config["site"],
        ),
        mimetype="text/xml",
    )
