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

from warehouse.cache.origin.derivers import html_cache_deriver


def test_no_renderer():
    view = pretend.stub()
    info = pretend.stub(options={})

    assert html_cache_deriver(view, info) == view


def test_non_html_renderer():
    view = pretend.stub()
    renderer = pretend.stub(name='foo.txt')
    info = pretend.stub(options={'renderer': renderer})

    assert html_cache_deriver(view, info) == view


def test_no_origin_cache_found():
    view_result = pretend.stub()
    view = pretend.call_recorder(lambda context, request: view_result)
    renderer = pretend.stub(name='foo.html')
    info = pretend.stub(options={'renderer': renderer})
    context = pretend.stub()

    def raise_valueerror(*a):
        raise ValueError

    request = pretend.stub(
        find_service=raise_valueerror,
        add_response_callback=pretend.call_recorder(lambda a: None)
    )

    assert html_cache_deriver(view, info)(context, request) == view_result
    assert request.add_response_callback.calls == []


def test_response_hook():

    class Cache:

        @staticmethod
        @pretend.call_recorder
        def cache(keys, request, response):
            pass

    response = pretend.stub()

    @pretend.call_recorder
    def view(context, request):
        return response

    context = pretend.stub()
    cacher = Cache()
    callbacks = []
    request = pretend.stub(
        find_service=lambda iface: cacher,
        add_response_callback=callbacks.append,
    )
    info = pretend.stub(options={'renderer': pretend.stub(name='foo.html')})
    derived_view = html_cache_deriver(view, info)

    assert derived_view(context, request) is response
    assert view.calls == [pretend.call(context, request)]
    assert len(callbacks) == 1

    callbacks[0](request, response)

    assert cacher.cache.calls == [
        pretend.call(
            ['all-html', 'foo.html'],
            request,
            response,
        ),
    ]
