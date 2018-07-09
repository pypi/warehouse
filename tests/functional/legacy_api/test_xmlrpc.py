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

import pretend
import pytest


def test_xmlrpc_raises_fault(app_config, webtest):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "list_packages", "one", "two")
    assert app_config.registry.datadog.increment.calls == [
        pretend.call("warehouse.xmlrpc.call", tags=["rpc_method:list_packages"])
    ]
    assert app_config.registry.datadog.timed.calls == [
        pretend.call("warehouse.xmlrpc.timing", tags=["rpc_method:list_packages"])
    ]


def test_xmlrpc_nomethod(app_config, webtest):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "multipassssss")
    assert app_config.registry.datadog.increment.calls == []
    assert app_config.registry.datadog.timed.calls == []


def test_xmlrpc_succeeds(app_config, webtest):
    webtest.xmlrpc("/pypi", "changelog_last_serial")
    assert app_config.registry.datadog.increment.calls == [
        pretend.call("warehouse.xmlrpc.call", tags=["rpc_method:changelog_last_serial"])
    ]
    assert app_config.registry.datadog.timed.calls == [
        pretend.call(
            "warehouse.xmlrpc.timing", tags=["rpc_method:changelog_last_serial"]
        )
    ]
