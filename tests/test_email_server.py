import pretend

from warehouse.email_server import EmailServer


def test_disabled_send_email():
    """ when a email server is disabled, nothing should be sent """
    config = {
        'disabled': True
    }
    server = EmailServer(config)
    server.send_message("foo")


def test_send_email():
    """ when a email server is not disabled, the body should be sent """
    email_class = lambda url: pretend.stub(
        send_message=pretend.call_recorder(lambda msg: None)
    )

    config = {
        'disabled': False,
        'url': 'not_used'
    }
    server = EmailServer(config, email_class=email_class)
    server.send_message("foo")
    assert server._smtp_server.send_message.calls == [pretend.call("foo")]
