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

from warehouse.cache.http import add_vary, cache_control, surrogate_control


@pytest.mark.parametrize("vary", [None, [], ["wat"]])
def test_add_vary(vary):
    class FakeRequest:

        def __init__(self):
            self.callbacks = []

        def add_response_callback(self, callback):
            self.callbacks.append(callback)

    response = pretend.stub(vary=vary)
    context = pretend.stub()
    request = FakeRequest()

    def view(context, request):
        return response

    assert add_vary("foobar")(view)(context, request) is response
    assert len(request.callbacks) == 1

    request.callbacks[0](request, response)

    if vary is None:
        vary = []

    assert response.vary == {"foobar"} | set(vary)


class TestCacheControl:

    def test_cache_public(self):
        response_obj = pretend.stub(
            cache_control=pretend.stub(public=None, max_age=None),
        )
        request_obj = pretend.stub(registry=pretend.stub(settings={}))
        context_obj = pretend.stub()

        @cache_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
        assert response.cache_control.public
        assert response.cache_control.max_age == 12

    def test_cache_private(self):
        response_obj = pretend.stub(
            cache_control=pretend.stub(private=None, max_age=None),
        )
        request_obj = pretend.stub(registry=pretend.stub(settings={}))
        context_obj = pretend.stub()

        @cache_control(12, public=False)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
        assert response.cache_control.private
        assert response.cache_control.max_age == 12

    def test_no_cache(self):
        response_obj = pretend.stub(
            cache_control=pretend.stub(
                no_cache=None,
                no_store=None,
                must_revalidate=None,
            ),
        )
        request_obj = pretend.stub(registry=pretend.stub(settings={}))
        context_obj = pretend.stub()

        @cache_control(False)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
        assert response.cache_control.no_cache
        assert response.cache_control.no_store
        assert response.cache_control.must_revalidate

    def test_bypass_cache(self):
        response_obj = pretend.stub()
        request_obj = pretend.stub(
            registry=pretend.stub(settings={"prevent_http_cache": True}),
        )
        context_obj = pretend.stub()

        @cache_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj


class TestSurrogateControl:

    def test_surrogate(self):
        response_obj = pretend.stub(headers={})
        request_obj = pretend.stub(registry=pretend.stub(settings={}))
        context_obj = pretend.stub()

        @surrogate_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
        assert response.headers["Surrogate-Control"] == "max-age=12"

    def test_bypass_cache(self):
        response_obj = pretend.stub()
        request_obj = pretend.stub(
            registry=pretend.stub(settings={"prevent_http_cache": True}),
        )
        context_obj = pretend.stub()

        @surrogate_control(12)
        def view(context, request):
            assert context is context_obj
            assert request is request_obj
            return response_obj

        response = view(context_obj, request_obj)

        assert response is response_obj
