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

import re
from SimpleXMLRPCServer import SimpleXMLRPCDispatcher

import arrow
from werkzeug.exceptions import BadRequest

from warehouse.http import Response


def handle_request(app, request):
    '''Wrap an invocation of the XML-RPC dispatcher.
    '''
    dispatcher = SimpleXMLRPCDispatcher()
    dispatcher.register_instance(Interface(app, request))

    # read in the XML-RPC request data, limiting to a sensible size
    if int(request.headers['Content-Length']) > 10 * 1024 * 1024:
        raise BadRequest('request data too large')
    xml_request = request.get_data(cache=False, as_text=True)

    # errors here are handled by _marshaled_dispatch
    response = dispatcher._marshaled_dispatch(xml_request)
    # legacy; remove non-printable ASCII control codes from the response
    response = re.sub('([\x00-\x08]|[\x0b-\x0c]|[\x0e-\x1f])+', '', response)

    return Response(response, mimetype="text/xml")


class Interface(object):
    def __init__(self, app, request):
        self.app = app
        self.request = request

    def list_packages(self):
        return self.app.models.packaging.all_projects()

    def list_packages_with_serial(self):
        return self.app.models.packaging.get_projects_with_serial()

    def top_packages(self, num=None):
        return self.app.models.packaging.get_top_projects(num)

    def user_packages(self, user):
        result = self.app.models.packaging.get_roles_for_user(user)
        return [(r['package_name'], r['role_name']) for r in result]

    def package_releases(self, name, show_hidden=False):
        return self.app.models.packaging.get_project_versions(name)

    def package_roles(self, name):
        result = self.app.models.packaging.get_roles_for_project(name)
        return [(r['user_name'], r['role_name']) for r in result]

    def package_hosting_mode(self, name):
        return self.app.models.packaging.get_hosting_mode(name)

    def updated_releases(self, since):
        since = arrow.get(since).datetime
        result = self.app.models.packaging.get_releases_since(since)
        return [(row['name'], row['version']) for row in result]

    def changed_packages(self, since):
        since = arrow.get(since).datetime
        return self.app.models.packaging.get_changed_since(since)

    def changelog(self, since, with_ids=False):
        since = arrow.get(since).datetime
        result = self.app.models.packaging.get_changelog(since)
        keys = 'name version submitted_date action'.split()
        if with_ids:
            keys.append('id')
        mapped = []
        for row in result:
            row['submitted_date'] = arrow.get(row['submitted_date']).timestamp
            mapped.append(tuple(row[key] for key in keys))
        return mapped

    def changelog_last_serial(self):
        return self.app.models.packaging.get_last_changelog_serial()

    def changelog_since_serial(self, since):
        result = self.app.models.packaging.get_changelog_serial(since)
        keys = 'name version submitted_date action id'.split()
        mapped = []
        for row in result:
            row['submitted_date'] = arrow.get(row['submitted_date']).timestamp
            mapped.append(tuple(row[key] for key in keys))
        return mapped

    def release_urls(self, name, version):
        l = []
        for r in self.app.models.packaging.get_downloads(name, version):
            l.append(dict(
                url=r['url'],
                packagetype=r['packagetype'],
                filename=r['filename'],
                size=r['size'],
                md5_digest=r['md5_digest'],
                downloads=r['downloads'],
                has_sig=r['pgp_url'] is not None,
                python_version=r['python_version'],
                comment_text=r['comment_text'],
            ))
        return l

    def release_downloads(self, name, version):
        results = self.app.models.packaging.get_downloads(name, version)
        return [(r['filename'], r['downloads']) for r in results]

    def release_data(self, name, version):
        model = self.app.models.packaging
        try:
            info = model.get_release(name, version)
        except IndexError:
            # the CURRENT model code will raise an IndexError on missing
            # package but this should be altered
            return {}

        info['stable_version'] = ''     # legacy; never actually correct
        info['classifiers'] = model.get_classifiers(name, version)
        info['package_url'] = 'http://pypi.python.org/pypi/%s' % name
        info['release_url'] = 'http://pypi.python.org/pypi/%s/%s' % (name,
            version)
        info['docs_url'] = model.get_documentation_url(name)
        info['downloads'] = model.get_download_counts(name)

        # XML-RPC has no datetime; work only with UNIX timestamps
        info['created'] = arrow.get(info['created']).timestamp

        # make the data XML-RPC-happy (no explicit null allowed here!)
        for k in info:
            if info[k] is None:
                info[k] = ''

        return info

    def browse(self, categories):
        if not isinstance(categories, list):
            raise TypeError("Parameter categories must be a list")

        model = self.app.models.packaging
        classifier_ids = model.get_classifier_ids(categories)
        if len(classifier_ids) != len(categories):
            missing = list(set(categories) - set(classifier_ids))
            missing = ', '.join("%s" % c for c in missing)
            raise ValueError('Unknown classifier(s): ' + missing)

        return model.search_by_classifier(classifier_ids.values())
