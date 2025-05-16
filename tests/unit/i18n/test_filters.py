# SPDX-License-Identifier: Apache-2.0

import email.utils

import babel.dates
import babel.numbers
import pretend

from warehouse.i18n import filters


def test_format_date(monkeypatch):
    formatted = pretend.stub()
    format_date = pretend.call_recorder(lambda *a, **kw: formatted)
    monkeypatch.setattr(babel.dates, "format_date", format_date)

    request = pretend.stub(locale=pretend.stub())
    ctx = pretend.stub(get=pretend.call_recorder(lambda k: request))

    args = [pretend.stub(), pretend.stub()]
    kwargs = {"foo": pretend.stub()}

    assert filters.format_date(ctx, *args, **kwargs) is formatted

    kwargs.update({"locale": request.locale})
    assert format_date.calls == [pretend.call(*args, **kwargs)]


def test_format_datetime(monkeypatch):
    formatted = pretend.stub()
    format_datetime = pretend.call_recorder(lambda *a, **kw: formatted)
    monkeypatch.setattr(babel.dates, "format_datetime", format_datetime)

    request = pretend.stub(locale=pretend.stub())
    ctx = pretend.stub(get=pretend.call_recorder(lambda k: request))

    args = [pretend.stub(), pretend.stub()]
    kwargs = {"foo": pretend.stub()}

    assert filters.format_datetime(ctx, *args, **kwargs) is formatted

    kwargs.update({"locale": request.locale})
    assert format_datetime.calls == [pretend.call(*args, **kwargs)]


def test_format_rfc822_datetime(monkeypatch):
    formatted = pretend.stub()
    formatdate = pretend.call_recorder(lambda *a, **kw: formatted)
    monkeypatch.setattr(email.utils, "formatdate", formatdate)

    ctx = pretend.stub()
    timestamp = pretend.stub()
    args = [pretend.stub(timestamp=lambda: timestamp), pretend.stub()]
    kwargs = {"foo": pretend.stub()}

    assert filters.format_rfc822_datetime(ctx, *args, **kwargs) is formatted
    assert formatdate.calls == [pretend.call(timestamp, usegmt=True)]


def test_format_number(monkeypatch):
    formatted = pretend.stub()
    format_number = pretend.call_recorder(lambda *a, **kw: formatted)
    monkeypatch.setattr(babel.numbers, "format_decimal", format_number)

    request = pretend.stub(locale=pretend.stub())
    ctx = pretend.stub(get=pretend.call_recorder(lambda k: request))

    number = pretend.stub()
    locale = request.locale

    assert filters.format_number(ctx, number) is formatted
    assert filters.format_number(ctx, number, locale="tr-TR") is formatted
    assert format_number.calls == [
        pretend.call(number, locale=locale),
        pretend.call(number, locale="tr-TR"),
    ]
