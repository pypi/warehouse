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

from warehouse.helpdesk import includeme
from warehouse.helpdesk.interfaces import IHelpDeskService


def test_includeme():
    helpdesk_class = pretend.stub(create_service=pretend.stub())
    config = pretend.stub(
        registry=pretend.stub(settings={"helpdesk.backend": "tests.CustomBackend"}),
        maybe_dotted=pretend.call_recorder(lambda n: helpdesk_class),
        register_service_factory=pretend.call_recorder(lambda s, i, **kw: None),
    )

    includeme(config)

    assert config.maybe_dotted.calls == [pretend.call("tests.CustomBackend")]
    assert config.register_service_factory.calls == [
        pretend.call(helpdesk_class.create_service, IHelpDeskService)
    ]
