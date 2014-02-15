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

import hashlib
import json
import os.path
import urllib
import urlparse
import re

import warehouse.application


def url_for(request, endpoint, **values):
    force_external = values.pop("_force_external", False)
    return request.url_adapter.build(
        endpoint, values,
        force_external=force_external,
    )


def gravatar_url(email, size=80):
    if email is None:
        email = ""

    email_hash = hashlib.md5(email.strip().lower()).hexdigest()

    url = "https://secure.gravatar.com/avatar/{}".format(email_hash)
    params = {
        "size": size,
    }

    return "?".join([url, urllib.urlencode(params)])


def static_url(app, filename):
    """
    static_url('css/bootstrap.css')
    """
    static_dir = os.path.join(
        os.path.dirname(os.path.abspath(warehouse.application.__file__)),
        "static",
        "compiled",
    )

    filepath = os.path.join(static_dir, filename)
    manifest_path = os.path.join(os.path.dirname(filepath), ".manifest.json")

    if not app.config.debug:
        # Load our on disk manifest
        with open(manifest_path) as fp:
            manifest = json.load(fp)

        # Get the base name for this file
        basename = manifest.get(os.path.basename(filename))

        # If we were able to get a base name, then create a filename with it
        if basename is not None:
            filename = os.path.join(os.path.dirname(filename), basename)

    return urlparse.urljoin("/static/", filename)
