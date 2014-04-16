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

import pytest

from warehouse.packaging.helpers import (get_description_urls,
                                         normalize_package_name,
                                         package_type_display,
                                         process_description_to_html,
                                         trim_docstring,
                                         xmlescape)


@pytest.mark.parametrize(("package_type", "display"), [
    ("sdist", "Source"),
    ("bdist_dumb", "\"dumb\" binary"),
    ("bdist_rpm", "RPM"),
    ("bdist_wininst", "Windows Installer"),
    ("bdist_msi", "Windows MSI Installer"),
    ("bdist_egg", "Egg"),
    ("bdist_dmg", "OSX Disk Image"),
    ("bdist_wheel", "Wheel"),
    ("unknown", "unknown"),
])
def test_package_type_display(package_type, display):
    assert package_type_display(package_type) == display


def test_normalize_package_name():
    assert normalize_package_name("scooby^dooby*doo") == "scooby-dooby-doo"
    assert normalize_package_name("Scooby^Dooby*doo") == "scooby-dooby-doo"
    assert normalize_package_name("test_this") == "test-this"
    assert normalize_package_name("hoobs#") == "hoobs-"
    assert normalize_package_name("Hoobs#") == "hoobs-"


def test_trim_docstring():
    assert trim_docstring("") == ""
    TEST_DOCSTRING = """ Testing
    this
      thing
    """
    assert trim_docstring(TEST_DOCSTRING) == """
Testing
this
  thing
""".strip()


def test_process_description_to_html():
    input_string = \
        """
        ===
        foo
        ===

        ---
        bar
        ---

        baz
        ===""".strip()

    output_string = \
        """
<div class="section" id="baz">
<h1>baz</h1>
</div>""".strip()
    assert process_description_to_html(input_string) == output_string


def test_xmlescape():
    assert xmlescape("http://myface.badsymbols.<><>") == "http://myface.badsymbols.&lt;&gt;&lt;&gt;"


def test_get_description_urls():
    assert get_description_urls("`foo <http://myface.badsymbols>`_") == ['http://myface.badsymbols']
