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


VALID_CALLBACK_RE = re.compile(r'^[$a-z_][0-9a-z_\.\[\]]*$', re.I)

# Reserved words list from http://javascript.about.com/library/blreserved.htm
JSONP_RESERVED_WORDS = frozenset((
    'abstract', 'boolean', 'break', 'byte', 'case', 'catch', 'char', 'class',
    'const', 'continue', 'debugger', 'default', 'delete', 'do', 'double',
    'else', 'enum', 'export', 'extends', 'false', 'final', 'finally', 'float',
    'for', 'function', 'goto', 'if', 'implements', 'import', 'in',
    'instanceof', 'int', 'interface', 'long', 'native', 'new', 'null',
    'package', 'private', 'protected', 'public', 'return', 'short', 'static',
    'super', 'switch', 'synchronized', 'this', 'throw', 'throws', 'transient',
    'true', 'try', 'typeof', 'var', 'void', 'volatile', 'while', 'with',
))


def is_valid_json_callback_name(callback_name):
    if not callback_name:
        return False

    # Callbacks longer than 50 characters are suspicious.
    # There isn't a legit reason for a callback longer.
    # The length is arbitrary too.
    # It's technically possible to construct malicious payloads using
    # only ascii characters, so we just block this.
    if len(callback_name) > 50:
        return False

    if not VALID_CALLBACK_RE.match(callback_name):
        return False

    if callback_name in JSONP_RESERVED_WORDS:
        return False

    return True
