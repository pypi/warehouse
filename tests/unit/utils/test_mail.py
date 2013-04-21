import pytest

from unittest import mock

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
    instance = mock.NonCallableMock()
    instance.send = mock.Mock()
    mock_message = mock.Mock(return_value=instance)

    # Try to send a mail message
    send_mail(recipients, subject, message, from_address,
                message_class=mock_message,
            )

    assert mock_message.call_count == 1
    assert mock_message.call_args == (
                                (subject, message, from_address, recipients),
                                {},
                            )

    assert instance.send.call_count == 1
    assert instance.send.call_args == (tuple(), {})
