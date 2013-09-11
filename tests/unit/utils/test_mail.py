# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pretend
import pytest

from warehouse.utils.mail import send_mail


@pytest.mark.parametrize(
    ("recipients", "subject", "message", "from_address"),
    [
        (["foo@example.com"], "Testing", "My Message", None),
        (["foo@example.com"], "Testing", "My Message", "no-reply@example.com"),
    ],
)
def test_send_mail(recipients, subject, message, from_address):
    # Set up our FakeClass
    instance = pretend.stub(
        send=pretend.call_recorder(lambda *args, **kwargs: None),
    )
    message = pretend.call_recorder(lambda *args, **kwargs: instance)

    # Try to send a mail message
    send_mail(recipients, subject, message, from_address,
        message_class=message,
    )

    assert message.calls == [
        pretend.call(subject, message, from_address, recipients),
    ]
    assert instance.send.calls == [pretend.call()]
