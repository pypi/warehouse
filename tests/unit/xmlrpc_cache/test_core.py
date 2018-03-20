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

import pretend
import pytest

from pyramid.exceptions import ConfigurationError

from warehouse import xmlrpc_cache
from warehouse.xmlrpc_cache import (
    RedisXMLRPCCache,
    NullXMLRPCCache,
    IXMLRPCCache,
)


class TestXMLRPCCache:

    def test_null_cache(self):
        service = NullXMLRPCCache()

        def test_func(arg0, arg1, kwarg0=0, kwarg1=1):
            return ((arg0, arg1), {'kwarg0': kwarg0, 'kwarg1': kwarg1})

        assert service.fetch(
            test_func, (1, 2), {'kwarg0': 3, 'kwarg1': 4}, None, None, None) \
            == ((1, 2), {'kwarg0': 3, 'kwarg1': 4})

        assert service.purge(None) is None


class TestIncludeMe:

    @pytest.mark.parametrize(
        ('url', 'cache_class'),
        [
            ('redis://', 'RedisXMLRPCCache'),
            ('rediss://', 'RedisXMLRPCCache'),
            ('null://', 'NullXMLRPCCache'),
        ]
    )
    def test_configuration(self, url, cache_class, monkeypatch):
        client_obj = pretend.stub()
        client_cls = pretend.call_recorder(lambda *a, **kw: client_obj)
        monkeypatch.setattr(xmlrpc_cache, cache_class, client_cls)

        registry = {}
        config = pretend.stub(
            add_view_deriver=pretend.call_recorder(
                lambda deriver, over=None, under=None: None
            ),
            register_service=pretend.call_recorder(
                lambda service, iface=None: None
            ),
            registry=pretend.stub(
                settings={"xmlrpc_cache.url": url},
                __setitem__=registry.__setitem__,
            ),
        )

        xmlrpc_cache.includeme(config)

        assert config.register_service.calls == [
            pretend.call(client_obj, iface=IXMLRPCCache)
        ]
        assert config.add_view_deriver.calls == [
            pretend.call(
                xmlrpc_cache.cached_return_view,
                under='rendered_view', over='mapped_view'
            )
        ]

    def test_bad_url_configuration(self, monkeypatch):
        registry = {}
        config = pretend.stub(
            add_view_deriver=pretend.call_recorder(
                lambda deriver, over=None, under=None: None
            ),
            register_service=pretend.call_recorder(
                lambda service, iface=None: None
            ),
            registry=pretend.stub(
                settings={
                    "xmlrpc_cache.url": "memcached://",
                },
                __setitem__=registry.__setitem__,
            )
        )

        with pytest.raises(ConfigurationError) as excinfo:
            xmlrpc_cache.includeme(config)

    def test_bad_expires_configuration(self, monkeypatch):
        client_obj = pretend.stub()
        client_cls = pretend.call_recorder(lambda *a, **kw: client_obj)
        monkeypatch.setattr(xmlrpc_cache, "NullXMLRPCCache", client_cls)

        registry = {}
        config = pretend.stub(
            add_view_deriver=pretend.call_recorder(
                lambda deriver, over=None, under=None: None
            ),
            register_service=pretend.call_recorder(
                lambda service, iface=None: None
            ),
            registry=pretend.stub(
                settings={
                    "xmlrpc_cache.url": "null://",
                    "xmlrpc_cache.expires": "Never",
                },
                __setitem__=registry.__setitem__,
            ),
        )

        with pytest.raises(ConfigurationError) as excinfo:
            xmlrpc_cache.includeme(config)
