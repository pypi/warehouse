# SPDX-License-Identifier: Apache-2.0

import binascii
import collections
import datetime
import enum
import hmac
import json
import re
import urllib.parse

from email.utils import getaddresses

import html5lib
import html5lib.serializer
import html5lib.treewalkers
import jinja2
import packaging_legacy.version
import pytz

from natsort import natsorted
from pyramid.threadlocal import get_current_request
from urllib3.util import parse_url

from warehouse.utils.http import is_valid_uri


_HOME_NAMES = ("home", "homepage", "home page")
_CHANGELOG_NAMES = (
    "changelog",
    "change log",
    "changes",
    "release notes",
    "news",
    "what's new",
    "history",
)
_DOC_HOST_EXACT = ("readthedocs.io", "readthedocs.org", "rtfd.io", "rtfd.org")
_DOC_HOST_SUFFIXES = (".readthedocs.io", ".readthedocs.org", ".rtfd.io", ".rtfd.org")
_DOC_HOST_PREFIXES = ("docs.", "documentation.")
_BUG_NAMES_START = ("bug", "issue", "tracker", "report")
_FUNDING_NAMES_START = ("funding", "donate", "donation", "sponsor")
_GITHUB_HOST_SUFFIXES = ("github.com", "github.io")
_GITLAB_HOST = "gitlab.com"
_GITTER_HOST_SUFFIX = "gitter.im"
_DISCORD_HOSTS = ("discord.com", "discordapp.com", "discord.gg")
_GOOGLE_HOST_SUFFIX = ".google.com"
_BITBUCKET_HOST = "bitbucket.org"
_REDDIT_HOST_SUFFIX = ".reddit.com"
_SLACK_HOST = "slack.com"
_TWITTER_HOSTS = ("twitter.com", "x.com")
_BLSKY_HOST = "bsky.app"
_CI_HOST_SUFFIXES = (
    "ci.appveyor.com",
    "circleci.com",
    "codecov.io",
    "coveralls.io",
    "travis-ci.com",
    "travis-ci.org",
)
_PYPI_HOSTS = ("cheeseshop.python.org", "pypi.io", "pypi.org", "pypi.python.org")
_PYTHON_ORG_SUFFIX = ".python.org"
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


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

    path = "/".join(
        [
            hmac.new(camo_key, url, digestmod="sha1").hexdigest(),
            binascii.hexlify(url).decode("utf8"),
        ]
    )

    return urllib.parse.urljoin(camo_url, path)


@jinja2.pass_context
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
            return f"{magnitude:.3g}{symbol}"

    return str(value)


def tojson(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def urlparse(value):
    return parse_url(value)


def format_tags(tags):
    # split tags
    if re.search(r",", tags):
        split_tags = re.split(r"\s*,\s*", tags)
    elif re.search(r";", tags):
        split_tags = re.split(r"\s*;\s*", tags)
    else:
        split_tags = re.split(r"\s+", tags)

    # strip whitespace, quotes, double quotes
    stripped_tags = [re.sub(r'^["\'\s]+|["\'\s]+$', "", t) for t in split_tags]

    # remove any empty tags
    formatted_tags = [t for t in stripped_tags if t]

    return formatted_tags


def format_classifiers(classifiers):
    structured: collections.OrderedDict[str, list[str]] = collections.OrderedDict()

    # Split up our classifiers into our data structure
    for classifier in classifiers:
        key, *value = classifier.split(" :: ", 1)
        if value:
            if key not in structured:
                structured[key] = []
            structured[key].append(value[0])

    # Sort all the values in our data structure
    for key, value in structured.items():
        structured[key] = natsorted(value)

    return structured


def classifier_id(classifier):
    return classifier.replace(" ", "_").replace("::", ".")


def contains_valid_uris(items):
    """Returns boolean representing whether the input list contains any valid
    URIs
    """
    return any(is_valid_uri(i) for i in items)


def parse_version(version_str):
    return packaging_legacy.version.parse(version_str)


def localize_datetime(timestamp):
    return pytz.utc.localize(timestamp)


def ctime(timestamp):
    return datetime.datetime.fromtimestamp(timestamp)


def is_recent(timestamp):
    if timestamp:
        return timestamp + datetime.timedelta(days=30) > datetime.datetime.now()
    return False


def parse_isoformat(datestring):
    return datetime.datetime.fromisoformat(datestring)


def format_email(metadata_email: str) -> tuple[str, str]:
    """
    Return the name and email address from a metadata RFC-822 string.
    Use Jinja's `first` and `last` to access each part in a template.
    TODO: Support more than one email address, per RFC-822.
    """
    emails = []
    for name, email in getaddresses([metadata_email]):
        if "@" not in email:
            return name, ""
        emails.append((name, email))
    return emails[0][0], emails[0][1]


def remove_invalid_xml_unicode(value: str | None) -> str | None:
    """
    Remove invalid unicode characters from a string.
    Useful for XML Templates.

    Ref: https://www.w3.org/TR/REC-xml/#NT-Char
    """
    return "".join(c for c in value if ord(c) >= 32) if value else value


def _canonical_url(request, **kwargs):
    if request.matched_route:
        try:
            return request.route_url(request.matched_route.name, **kwargs)
        except KeyError:
            pass


def url_icon(name, url):
    """Return a font-awesome icon markup for a URL based on its name or host."""
    if icon := icon_name(name, url):
        return jinja2.Markup(f'<i class="{icon}" aria-hidden="true"></i>')
    return jinja2.Markup("")


def icon_name(name, url):
    """Return the font-awesome icon class name for a URL based on its name or host.

    Returns None when both `name` and `url` are falsy to allow fast early
    returns by callers.
    """
    name_lower = (name or "").lower()

    if name_lower == "download":
        return "fas fa-cloud-download-alt"
    if name_lower == "bluesky":
        return "fab fa-bluesky"
    if name_lower == "mastodon":
        return "fab fa-mastodon"
    if name_lower in _HOME_NAMES:
        return "fas fa-home"
    if name_lower in _CHANGELOG_NAMES:
        return "fas fa-scroll"
    if name_lower.startswith(("docs", "documentation")):
        return "fas fa-book"
    if name_lower.startswith(_BUG_NAMES_START):
        return "fas fa-bug"
    if name_lower.startswith(_FUNDING_NAMES_START):
        return "fas fa-donate"

    try:
        parsed = urllib.parse.urlparse(url or "")
    except Exception:
        return None

    host = parsed.hostname.lower()
    if host in _GITHUB_HOST_SUFFIXES or host.endswith(_GITHUB_HOST_SUFFIXES):
        return "fab fa-github"
    if host == _GITLAB_HOST or host.endswith(".gitlab.com"):
        return "fab fa-gitlab"
    if host == _GITTER_HOST_SUFFIX or host.endswith(".gitter.im"):
        return "fab fa-gitter"
    if host in _DISCORD_HOSTS:
        return "fab fa-discord"
    if host == "google.com" or host.endswith(_GOOGLE_HOST_SUFFIX):
        return "fab fa-google"
    if host == _BITBUCKET_HOST or host.endswith(".bitbucket.org"):
        return "fab fa-bitbucket"
    if host == "reddit.com" or host.endswith(_REDDIT_HOST_SUFFIX):
        return "fab fa-reddit-alien"
    if (
        host == _SLACK_HOST
        or host.endswith(".slack.com")
        or name_lower.startswith("slack")
    ):
        return "fab fa-slack"
    if host in _TWITTER_HOSTS or host.endswith(_TWITTER_HOSTS):
        return "fab fa-twitter"
    if host == _BLSKY_HOST:
        return "fab fa-bluesky"
    if host.endswith(_CI_HOST_SUFFIXES):
        return "fas fa-tasks"
    if host in _PYPI_HOSTS or host.endswith(_PYPI_HOSTS):
        return "fas fa-cube"
    if host == "python.org" or host.endswith(_PYTHON_ORG_SUFFIX):
        return "fab fa-python"
    if host in _YOUTUBE_HOSTS or host.endswith(_YOUTUBE_HOSTS):
        return "fab fa-youtube"
    if (
        host in _DOC_HOST_EXACT
        or host.endswith(_DOC_HOST_SUFFIXES)
        or host.startswith(_DOC_HOST_PREFIXES)
    ):
        return "fas fa-book"
    return "fas fa-external-link-square-alt"


def includeme(config):
    config.add_request_method(_camo_url, name="camo_url")
    config.add_request_method(_canonical_url, name="canonical_url")
