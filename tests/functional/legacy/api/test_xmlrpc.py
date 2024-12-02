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


def test_xmlrpc_raises_fault(webtest):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "list_packages", "one", "two")


def test_xmlrpc_nomethod(webtest, metrics):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "multipassssss")
    assert metrics.increment.calls == []
    assert metrics.timed.calls == []


def test_xmlrpc_succeeds(webtest):
    webtest.xmlrpc("/pypi", "changelog_last_serial")


def test_invalid_arguments(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; package_name: Missing required argument",
    ):
        webtest.xmlrpc("/pypi", "package_releases")


def test_excess_arguments(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; 1: Unexpected positional argument",
    ):
        webtest.xmlrpc("/pypi", "changelog_last_serial", 1)


def test_arguments_with_wrong_type(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; serial: Input should be a valid integer",
    ):
        webtest.xmlrpc("/pypi", "changelog_since_serial", "wrong!")


def test_multiple_garbage_types(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=(
            r"client error; since: Input should be a valid integer; with_ids: "
            r"Input should be a valid boolean"
        ),
    ):
        webtest.xmlrpc("/pypi", "changelog", "wrong!", "also wrong!")
