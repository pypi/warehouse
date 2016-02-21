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

import binascii
import hmac
import json
import re
import urllib.parse

import html5lib
import html5lib.serializer
import html5lib.treewalkers
import jinja2

import readme_renderer.rst
import readme_renderer.txt

from pyramid.threadlocal import get_current_request


def _camo_url(camo_url, camo_key, url):
    camo_key = camo_key.encode("utf8")
    url = url.encode("utf8")

    path = "/".join([
        hmac.new(camo_key, url, digestmod="sha1").hexdigest(),
        binascii.hexlify(url).decode("utf8"),
    ])

    return urllib.parse.urljoin(camo_url, path)


@jinja2.contextfilter
def readme(ctx, value, *, format):
    request = ctx.get("request") or get_current_request()

    camo_url = request.registry.settings["camo.url"].format(request=request)
    camo_key = request.registry.settings["camo.key"]

    # The format parameter is here so we can more easily expand this to cover
    # READMEs which do not use restructuredtext, but for now rst is the only
    # format we support.
    assert format == "rst", "We currently only support rst rendering."

    # Actually render the given value, this will not only render the value, but
    # also ensure that it's had any disallowed markup removed.
    rendered = readme_renderer.rst.render(value)

    # If the content was not rendered, we'll replace the newlines with breaks
    # so that it shows up nicer when rendered.
    if rendered is None:
        rendered = readme_renderer.txt.render(value)

    # Parse the rendered output and replace any inline images that don't point
    # to HTTPS with camouflaged images.
    tree_builder = html5lib.treebuilders.getTreeBuilder("dom")
    parser = html5lib.html5parser.HTMLParser(tree=tree_builder)
    dom = parser.parse(rendered)

    for element in dom.getElementsByTagName("img"):
        src = element.getAttribute("src")
        if src:
            element.setAttribute("src", _camo_url(camo_url, camo_key, src))

    tree_walker = html5lib.treewalkers.getTreeWalker("dom")
    html_serializer = html5lib.serializer.htmlserializer.HTMLSerializer()
    rendered = "".join(html_serializer.serialize(tree_walker(dom)))

    return jinja2.Markup(rendered)


_SI_SYMBOLS = ["k", "M", "G", "T", "P", "E", "Z", "Y"]


def shorten_number(value):
    for i, symbol in enumerate(_SI_SYMBOLS):
        magnitude = value / (1000 ** (i + 1))
        if magnitude >= 1 and magnitude < 1000:
            return "{:.3g}{}".format(magnitude, symbol)

    return str(value)


def tojson(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def urlparse(value):
    return urllib.parse.urlparse(value)


def format_tags(tags):
    # split tags
    if re.search(r',', tags):
        split_tags = re.split(r'\s*,\s*', tags)
    elif re.search(r';', tags):
        split_tags = re.split(r'\s*;\s*', tags)
    else:
        split_tags = re.split(r'\s+', tags)

    # strip whitespace, quotes, double quotes
    stripped_tags = [re.sub(r'^["\'\s]+|["\'\s]+$', '', t) for t in split_tags]

    # remove any empty tags
    formatted_tags = [t for t in stripped_tags if t]

    return formatted_tags
