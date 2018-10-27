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

import xmlrpc.client

import pytest


def test_xmlrpc_raises_fault(app_config, webtest, metrics):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "list_packages", "one", "two")


def test_xmlrpc_nomethod(app_config, webtest, metrics):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "multipassssss")
    assert metrics.increment.calls == []
    assert metrics.timed.calls == []


def test_xmlrpc_succeeds(app_config, webtest, metrics):
    webtest.xmlrpc("/pypi", "changelog_last_serial")


def test_invalid_arguments(app_config, webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match="client error; missing a required argument: 'package_name'",
    ):
        webtest.xmlrpc("/pypi", "package_releases")


def test_arguments_with_wrong_type(app_config, webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match='client error; type of argument "serial" must be int; got str instead',
    ):
        webtest.xmlrpc("/pypi", "changelog_since_serial", "wrong!")
