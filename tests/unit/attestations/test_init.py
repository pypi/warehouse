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

from warehouse import attestations
from warehouse.attestations.interfaces import IIntegrityService


def test_includeme():
    fake_service_klass = pretend.stub(create_service=pretend.stub())
    config = pretend.stub(
        registry=pretend.stub(settings={"integrity.backend": "fake.path.to.backend"}),
        maybe_dotted=pretend.call_recorder(
            lambda attr: fake_service_klass,
        ),
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
    )

    attestations.includeme(config)

    assert config.maybe_dotted.calls == [pretend.call("fake.path.to.backend")]
    assert config.register_service_factory.calls == [
        pretend.call(fake_service_klass.create_service, IIntegrityService),
    ]
