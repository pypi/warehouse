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

import orjson
import pretend

from warehouse.api import config


def test_api_set_content_type():
    response = pretend.stub()

    @pretend.call_recorder
    def view(context, request):
        return response

    info = pretend.stub(options={"api_version": "v1"})
    wrapped_view = config._api_set_content_type(view, info)

    context = pretend.stub()
    request = pretend.stub(response=pretend.stub(content_type=None))

    assert wrapped_view(context, request) is response
    assert request.response.content_type == "application/vnd.pypi.v1+json"


def test_api_set_content_type_no_api_version():
    response = pretend.stub()

    @pretend.call_recorder
    def view(context, request):
        return response

    info = pretend.stub(options={})
    wrapped_view = config._api_set_content_type(view, info)

    context = pretend.stub()
    request = pretend.stub(response=pretend.stub(content_type=None))

    assert wrapped_view(context, request) is response
    assert request.response.content_type is None


def test_includeme():

    conf = pretend.stub(
        add_view_deriver=pretend.call_recorder(
            lambda deriver, over=None, under=None: None
        ),
        include=pretend.call_recorder(lambda x: None),
        pyramid_openapi3_spec=pretend.call_recorder(lambda *a, **kw: None),
        pyramid_openapi3_add_deserializer=pretend.call_recorder(lambda *a, **kw: None),
        pyramid_openapi3_add_explorer=pretend.call_recorder(lambda *a, **kw: None),
    )

    config.includeme(conf)

    assert conf.add_view_deriver.calls == [pretend.call(config._api_set_content_type)]
    assert conf.include.calls == [pretend.call("pyramid_openapi3")]
    assert conf.pyramid_openapi3_spec.calls == [
        pretend.call(
            "/opt/warehouse/src/warehouse/api/openapi.yaml", route="/api/openapi.yaml"
        )
    ]
    assert conf.pyramid_openapi3_add_deserializer.calls == [
        pretend.call("application/vnd.pypi.api-v0-danger+json", orjson.loads)
    ]
    assert conf.pyramid_openapi3_add_explorer.calls == [
        pretend.call(route="/api/explorer/")
    ]
