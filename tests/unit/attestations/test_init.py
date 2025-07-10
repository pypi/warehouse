# SPDX-License-Identifier: Apache-2.0

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
