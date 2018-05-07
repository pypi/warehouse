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
import collections
import enum
import hmac
import json
import re
import urllib.parse

import html5lib
import html5lib.serializer
import html5lib.treewalkers
import jinja2

import packaging.version

from pyramid.threadlocal import get_current_request

from warehouse.utils.http import is_valid_uri


class PackageType(enum.Enum):
    bdist_dmg = "OSX Disk Image"
    bdist_dumb = "Dumb Binary"
    bdist_egg = "Egg"
    bdist_msi = "Windows MSI Installer"
    bdist_rpm = "RPM"
    bdist_wheel = "Wheel"
    bdist_wininst = "Windows Installer"
    sdist = "Source"


def format_package_type(value):
    try:
        return PackageType[value].value
    except KeyError:
        return value


def _camo_url(request, url):
    camo_url = request.registry.settings["camo.url"].format(request=request)
    camo_key = request.registry.settings["camo.key"].encode("utf8")
    url = url.encode("utf8")

    path = "/".join([
        hmac.new(camo_key, url, digestmod="sha1").hexdigest(),
        binascii.hexlify(url).decode("utf8"),
    ])

    return urllib.parse.urljoin(camo_url, path)


@jinja2.contextfilter
def camoify(ctx, value):
    request = ctx.get("request") or get_current_request()

    # Parse the rendered output and replace any inline images that don't point
    # to HTTPS with camouflaged images.
    tree_builder = html5lib.treebuilders.getTreeBuilder("dom")
    parser = html5lib.html5parser.HTMLParser(tree=tree_builder)
    dom = parser.parse(value)

    for element in dom.getElementsByTagName("img"):
        src = element.getAttribute("src")
        if src:
            element.setAttribute("src", request.camo_url(src))

    tree_walker = html5lib.treewalkers.getTreeWalker("dom")
    html_serializer = html5lib.serializer.HTMLSerializer()
    camoed = "".join(html_serializer.serialize(tree_walker(dom)))

    return camoed


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


def format_classifiers(classifiers):
    structured = collections.defaultdict(list)

    # Split up our classifiers into our data structure
    for classifier in classifiers:
        key, *value = classifier.split(" :: ", 1)
        if value:
            structured[key].append(value[0])

    # Go thorugh and ensure that all of the lists in our classifiers are in
    # sorted order.
    structured = {k: sorted(v) for k, v in structured.items()}

    # Now, we'll ensure that our keys themselves are in sorted order, using an
    # OrderedDict to preserve this ordering when we pass this data back up to
    # our caller.
    structured = collections.OrderedDict(sorted(structured.items()))

    return structured


def contains_valid_uris(items):
    """Returns boolean representing whether the input list contains any valid
    URIs
    """
    return any(is_valid_uri(i) for i in items)


def parse_version(version_str):
    return packaging.version.parse(version_str)


def includeme(config):
    config.add_request_method(_camo_url, name="camo_url")
