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

import base64
import binascii
import collections
import functools
import hashlib
import hmac
import mimetypes
import os
import re
import urllib.parse

import html5lib
import html5lib.serializer
import html5lib.treewalkers

from werkzeug.urls import iri_to_uri
from werkzeug.utils import escape

from warehouse.http import Response


def merge_dict(base, additional):
    if base is None:
        return additional

    if additional is None:
        return base

    if not (isinstance(base, collections.Mapping)
            and isinstance(additional, collections.Mapping)):
        return additional

    merged = base
    for key, value in additional.items():
        if isinstance(value, collections.Mapping):
            merged[key] = merge_dict(merged.get(key), value)
        else:
            merged[key] = value

    return merged


def cache(browser=None, varnish=None):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(app, request, *args, **kwargs):
            resp = fn(app, request, *args, **kwargs)

            if 200 <= resp.status_code < 400:
                # Add in our standard Cache-Control headers
                if browser is not None:
                    resp.cache_control.public = True
                    resp.cache_control.max_age = browser

                # Add in additional headers if we're using varnish
                if varnish is not None:
                    resp.surrogate_control.public = True
                    resp.surrogate_control.max_age = varnish

            return resp
        return wrapper
    return deco


def get_wsgi_application(environ, app_class):
    if "WAREHOUSE_CONF" in environ:
        configs = [environ["WAREHOUSE_CONF"]]
    else:
        configs = []

    return app_class.from_yaml(*configs)


def get_mimetype(filename):
    # Figure out our mimetype
    mimetype = mimetypes.guess_type(filename)[0]
    if not mimetype:
        mimetype = "application/octet-stream"
    return mimetype


def redirect(location, code=302):
    """Return a response object (a WSGI application) that, if called,
    redirects the client to the target location.  Supported codes are 301,
    302, 303, 305, and 307.  300 is not supported because it's not a real
    redirect and 304 because it's the answer for a request with a request
    with defined If-Modified-Since headers.

    .. versionadded:: 0.6
       The location can now be a unicode string that is encoded using
       the :func:`iri_to_uri` function.

    :param location: the location the response should redirect to.
    :param code: the redirect status code. defaults to 302.
    """
    display_location = escape(location)
    if isinstance(location, str):
        location = iri_to_uri(location)
    response = Response(
        '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
        '<title>Redirecting...</title>\n'
        '<h1>Redirecting...</h1>\n'
        '<p>You should be redirected automatically to target URL: '
        '<a href="%s">%s</a>.  If not click the link.' %
        (escape(location), display_location), code, mimetype="text/html")
    response.headers["Location"] = location
    return response


def redirect_next(request, default="/", field_name="next", code=303):
    next = request.values.get(field_name)

    if not is_safe_url(next, request.host):
        next = default

    return redirect(next, code=code)


PACKAGE_REGEX = {
    "permitted_characters": re.compile("^[a-zA-Z0-9_\-.]+$"),
    "start_and_end_with_ascii": re.compile("^[a-zA-Z0-9].*[a-zA-Z0-9]$"),
}


def normalize_project_name(name):
    """
    Normalizes a package name as per PEP-426
    """
    name = re.sub("_", "-", name).lower()
    if not PACKAGE_REGEX["permitted_characters"].match(name):
        raise ValueError("name contains illegal characters! (See PEP-426)")
    if not PACKAGE_REGEX["start_and_end_with_ascii"].match(name):
        raise ValueError("Distribution names MUST start and end with " +
                         "an ASCII letter or digit (See PEP-426)")
    return name


class SearchPagination(object):

    def __init__(self, page, total, per_page, url):
        self.page = page
        self.total = total
        self.per_page = per_page
        self.url = url

    @property
    def pages(self):
        return max(0, self.total - 1) // self.per_page + 1

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_url(self):
        return self.url(page=self.page - 1)

    @property
    def next_url(self):
        return self.url(page=self.page + 1)


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


def generate_camouflage_url(camo_url, camo_key, url):
    digest = hmac.new(
        camo_key.encode("utf8"),
        url.encode("utf8"),
        digestmod=hashlib.sha1,
    ).hexdigest()
    return "".join([
        camo_url,
        "/".join([
            digest,
            binascii.hexlify(url.encode("utf8")).decode("utf8")
        ]),
    ])


def camouflage_images(camo_url, camo_key, html):
    # Parse SRC as HTML.
    tree_builder = html5lib.treebuilders.getTreeBuilder("dom")
    parser = html5lib.html5parser.HTMLParser(tree=tree_builder)
    dom = parser.parse(html)

    for e in dom.getElementsByTagName("img"):
        u = e.getAttribute("src")
        if u:
            e.setAttribute(
                "src",
                generate_camouflage_url(camo_url, camo_key, u),
            )

    tree_walker = html5lib.treewalkers.getTreeWalker("dom")
    html_serializer = html5lib.serializer.htmlserializer.HTMLSerializer()
    return "".join(html_serializer.serialize(tree_walker(dom)))


def cors(fn):
    @functools.wraps(fn)
    def wrapper(app, request, *args, **kwargs):
        # Get the response from the view
        resp = fn(app, request, *args, **kwargs)

        # Add our CORS headers
        resp.headers["Access-Control-Allow-Origin"] = "*"

        # Return the modified response
        return resp
    return wrapper


def vary_by(*varies):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(app, request, *args, **kwargs):
            # Get the response from the view
            resp = fn(app, request, *args, **kwargs)

            # Add our Vary headers
            resp.vary.update(varies)

            # Return the modified response
            return resp
        return wrapper
    return deco


def random_token(_urandom=os.urandom):
    token = base64.urlsafe_b64encode(_urandom(32)).rstrip(b"=")
    return token.decode("utf8")


def is_safe_url(url, host):
    """
    Return ``True`` if the url is a safe redirection (i.e. it doesn't point to
    a different host and uses a safe scheme).

    Always returns ``False`` on an empty url.
    """
    if not url:
        return False

    parsed = urllib.parse.urlparse(url)

    return ((not parsed.netloc or parsed.netloc == host) and
            (not parsed.scheme or parsed.scheme in ["http", "https"]))


def find_links_from_html(html_body):
    """
    Return a list of links, extracted from all <a href="{{ url
    }}">...</a> elements found.
    """
    document = html5lib.parse(html_body)
    return [a.attrib.get('href', None)
            for a in document.iter("{http://www.w3.org/1999/xhtml}a")
            if 'href' in a.attrib]
