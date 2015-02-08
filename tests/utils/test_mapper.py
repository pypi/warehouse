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

from unittest import mock

import pretend

from warehouse.utils.mapper import WarehouseMapper


class TestWarehouseMapper:

    def test_mapper_wraps_warehouse(self):
        mapper = WarehouseMapper()
        mapper._wrap_with_matchdict = pretend.call_recorder(lambda view: view)

        view = pretend.stub(__module__="warehouse.foo")
        mapper(view)

        assert mapper._wrap_with_matchdict.calls == [pretend.call(view)]

    def test_mapper_doesnt_wrap_non_warehouse(self):
        mapper = WarehouseMapper()
        mapper._wrap_with_matchdict = pretend.call_recorder(lambda view: view)

        view = pretend.stub(__module__="notwarehouse.foo")
        mapper(view)

        assert mapper._wrap_with_matchdict.calls == []

    def test_mapper_wrapped_function(self):
        mapper = WarehouseMapper()
        view = pretend.call_recorder(lambda request, foo: None)
        wrapped = mapper._wrap_with_matchdict(view)
        request = pretend.stub(matchdict={"foo": "bar"})
        wrapped(pretend.stub(), request)

        assert view.calls == [pretend.call(request, foo="bar")]

    def test_mapper_wrapped_class_no_attr(self):
        class View:

            @pretend.call_recorder
            def __init__(self, request):
                self.request = request

            @pretend.call_recorder
            def __call__(self, foo):
                pass

        mapper = WarehouseMapper()
        wrapped = mapper._wrap_with_matchdict(View)
        request = pretend.stub(matchdict={"foo": "bar"})
        wrapped(pretend.stub(), request)

        assert View.__init__.calls == [pretend.call(mock.ANY, request)]
        assert View.__call__.calls == [pretend.call(mock.ANY, foo="bar")]

    def test_mapper_wrapped_class_with_attr(self):
        class View:

            @pretend.call_recorder
            def __init__(self, request):
                self.request = request

            @pretend.call_recorder
            def otherfunc(self, foo):
                pass

        mapper = WarehouseMapper(attr="otherfunc")
        wrapped = mapper._wrap_with_matchdict(View)
        request = pretend.stub(matchdict={"foo": "bar"})
        wrapped(pretend.stub(), request)

        assert View.__init__.calls == [pretend.call(mock.ANY, request)]
        assert View.otherfunc.calls == [pretend.call(mock.ANY, foo="bar")]
