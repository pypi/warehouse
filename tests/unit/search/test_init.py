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

from warehouse import search


def test_es(monkeypatch):
    search_obj = pretend.stub()
    index_obj = pretend.stub(
        doc_type=pretend.call_recorder(lambda d: None),
        search=pretend.call_recorder(lambda: search_obj),
        settings=pretend.call_recorder(lambda **kw: None),
    )
    index_cls = pretend.call_recorder(lambda name, using: index_obj)
    monkeypatch.setattr(search.utils, "Index", index_cls)

    doc_types = [pretend.stub(), pretend.stub()]

    client = pretend.stub()
    request = pretend.stub(
        registry={
            "elasticsearch.client": client,
            "elasticsearch.index": "warehouse",
            "search.doc_types": doc_types,
        },
    )

    es = search.es(request)

    assert es is search_obj
    assert index_cls.calls == [pretend.call("warehouse", using=client)]
    assert index_obj.doc_type.calls == [pretend.call(d) for d in doc_types]
    assert index_obj.settings.calls == [
        pretend.call(
            number_of_shards=1,
            number_of_replicas=0,
            refresh_interval="1s",
        )
    ]
    assert index_obj.search.calls == [pretend.call()]
