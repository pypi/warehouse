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
import cgi
import re
import sys
import io
from contextlib import contextmanager
from urllib.parse import urlparse
from xml.etree import ElementTree

import docutils
from docutils.core import publish_doctree, Publisher
from docutils.writers import get_writer_class
from docutils.transforms import TransformError, Transform

ALLOWED_SCHEMES = (
    'file', 'ftp', 'gopher', 'hdl', 'http', 'https',
    'imap', 'mailto', 'mms', 'news', 'nntp', 'prospero', 'rsync',
    'rtsp', 'rtspu', 'sftp', 'shttp', 'sip', 'sip', 'snews', 'svn',
    'svn+ssh', 'telnet', 'wais', 'irc'
)

rest_url_regex = re.compile("<(https?://.*?)>")


def package_type_display(package_type):
    return {
        "sdist": "Source",
        "bdist_dumb": "\"dumb\" binary",
        "bdist_rpm": "RPM",
        "bdist_wininst": "Windows Installer",
        "bdist_msi": "Windows MSI Installer",
        "bdist_egg": "Egg",
        "bdist_dmg": "OSX Disk Image",
        "bdist_wheel": "Wheel",
    }.get(package_type, package_type)


def normalize_package_name(name):
    """
    Any runs of non-alphanumeric/. characters are replaced with a single '-'.
    Return lower-cased version of safe_name of n.
    """
    return re.sub('[^A-Za-z0-9.]+', '-', name).lower()


def trim_docstring(text):
    """
    Trim indentation and blank lines from docstring text & return it.

    See PEP 257.
    """
    if not text:
        return text
    # Convert tabs to spaces (following the normal Python rules)
    # and split into a list of lines:
    lines = text.expandtabs().splitlines()
    # Determine minimum indentation (first line doesn't count):
    indent = -1
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
            if indent == -1:
                indent = len(line) - len(stripped)
    # Remove indentation (first line is special):
    trimmed = [lines[0].strip()]
    if indent != -1:
        for line in lines[1:]:
            trimmed.append(line[indent:].rstrip())
    # Strip off trailing and leading blank lines:
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    # Return a single string:
    return '\n'.join(trimmed)


@contextmanager
def _capture_stderr():
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    yield sys.stderr
    sys.stderr = old_stderr


def process_description_to_html(source, output_encoding='unicode'):
    """Given an source string, returns an HTML fragment as a string.

    The return value is the contents of the <body> tag.

    Parameters:

    - `source`: A multi-line text string; required.
    - `output_encoding`: The desired encoding of the output.  If a Unicode
      string is desired, use the default value of "unicode" .
    """
    # Dedent all lines of `source`.
    source = trim_docstring(source)

    settings_overrides = {
        'raw_enabled': 0,  # no raw HTML code
        'file_insertion_enabled': 0,  # no file/URL access
        'halt_level': 2,  # at warnings or errors, raise an exception
        'report_level': 5,  # never report problems with the reST code
    }

    parts = None

    # capture publishing errors, they go to stderr
    with _capture_stderr() as stderr:

        # Convert reStructuredText to HTML using Docutils.
        document = publish_doctree(
            source=source,
            settings_overrides=settings_overrides)

        for node in document.traverse():
            if node.tagname == '#text':
                continue
            if node.hasattr('refuri'):
                uri = node['refuri']
            elif node.hasattr('uri'):
                uri = node['uri']
            else:
                continue
            o = urlparse(uri)
            if o.scheme not in ALLOWED_SCHEMES:
                raise TransformError('link scheme not allowed')

        # now turn the transformed document into HTML
        reader = docutils.readers.doctree.Reader(parser_name='null')
        pub = Publisher(
            reader, source=docutils.io.DocTreeInput(document),
            destination_class=docutils.io.StringOutput
        )
        pub.set_writer('html')
        pub.process_programmatic_settings(None, settings_overrides, None)
        pub.set_destination(None, None)
        pub.publish()
        parts = pub.writer.parts

    # original text if publishing errors occur
    if parts is None or len(stderr.getvalue()) > 0:
        output = "".join('<PRE>\n' + cgi.escape(source) + '</PRE>').strip()
    else:
        output = parts['body'].strip()

    if output_encoding != 'unicode':
        output = output.encode(output_encoding).strip()

    return output


def xmlescape(url):
    '''
    Make sure a URL is valid XML
    (copied directly from pypi)
    '''
    try:
        ElementTree.fromstring('<x y="%s"/>' % url)
    except ElementTree.ParseError:
        return cgi.escape(url)
    else:
        return url


def get_description_urls(text):
    """ parse all urls from a body of text, html-escaped. """

    # a little history on this.
    # this is legacy behaviour from pypi, where the escaped versions
    # of urls were stored instead of the actual url themselves
    # we can't remove this behaviour in warehouse until pypi is deprecated,
    # since it interfere with html on the legacy pypi pages

    return [xmlescape(url) for url in rest_url_regex.findall(text)]
