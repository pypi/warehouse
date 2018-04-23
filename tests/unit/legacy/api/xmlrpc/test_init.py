import pretend
from pyramid.events import NewResponse

from warehouse.legacy.api.xmlrpc import on_new_response, includeme


def test_on_new_response_enabled():
    metric_name = pretend.stub()
    histogram = pretend.call_recorder(lambda metric_name, value: None)
    content_length = pretend.stub()
    new_response_event = pretend.stub(
        request=pretend.stub(
            content_length_metric_name=metric_name,
            registry=pretend.stub(datadog=pretend.stub(histogram=histogram)),
        ),
        response=pretend.stub(content_length=content_length)
    )

    on_new_response(new_response_event)

    assert histogram.calls == [
        pretend.call(metric_name, content_length),
    ]


def test_on_new_response_disabled():
    histogram = pretend.call_recorder(lambda metric_name, value: None)
    new_response_event = pretend.stub(
        request=pretend.stub(
            registry=pretend.stub(datadog=pretend.stub(histogram=histogram)),
        ),
    )

    on_new_response(new_response_event)

    assert histogram.calls == []


def test_includeme():
    config = pretend.stub(
        add_subscriber=pretend.call_recorder(lambda subscriber, iface: None),
    )

    includeme(config)

    assert config.add_subscriber.calls == [
        pretend.call(on_new_response, NewResponse),
    ]
