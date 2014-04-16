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
import re
import sys


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
