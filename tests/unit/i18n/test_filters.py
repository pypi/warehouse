# SPDX-License-Identifier: Apache-2.0

import datetime
import email.utils

import babel.dates
import babel.numbers

from warehouse.i18n import filters


def test_format_date(mocker, pyramid_request):
    format_date = mocker.patch.object(
        babel.dates, "format_date", return_value=mocker.sentinel.formatted
    )
    pyramid_request.locale = mocker.sentinel.locale
    ctx = {"request": pyramid_request}
    args = (mocker.sentinel.arg0, mocker.sentinel.arg1)

    assert filters.format_date(ctx, *args, foo=mocker.sentinel.foo) is (
        mocker.sentinel.formatted
    )
    format_date.assert_called_once_with(
        *args, foo=mocker.sentinel.foo, locale=mocker.sentinel.locale
    )


def test_format_datetime(mocker, pyramid_request):
    format_datetime = mocker.patch.object(
        babel.dates, "format_datetime", return_value=mocker.sentinel.formatted
    )
    pyramid_request.locale = mocker.sentinel.locale
    ctx = {"request": pyramid_request}
    args = (mocker.sentinel.arg0, mocker.sentinel.arg1)

    assert filters.format_datetime(ctx, *args, foo=mocker.sentinel.foo) is (
        mocker.sentinel.formatted
    )
    format_datetime.assert_called_once_with(
        *args, foo=mocker.sentinel.foo, locale=mocker.sentinel.locale
    )


def test_format_rfc822_datetime(mocker):
    formatdate = mocker.patch.object(
        email.utils, "formatdate", return_value=mocker.sentinel.formatted
    )
    dt = datetime.datetime(2024, 1, 1, 12, 0, 0)

    result = filters.format_rfc822_datetime(
        {}, dt, mocker.sentinel.extra, foo=mocker.sentinel.foo
    )

    assert result is mocker.sentinel.formatted
    formatdate.assert_called_once_with(dt.timestamp(), usegmt=True)


def test_format_number(mocker, pyramid_request):
    format_decimal = mocker.patch.object(
        babel.numbers, "format_decimal", return_value=mocker.sentinel.formatted
    )
    pyramid_request.locale = mocker.sentinel.locale
    ctx = {"request": pyramid_request}
    number = mocker.sentinel.number

    assert filters.format_number(ctx, number) is mocker.sentinel.formatted
    assert filters.format_number(ctx, number, locale="tr-TR") is (
        mocker.sentinel.formatted
    )
    assert format_decimal.call_args_list == [
        mocker.call(number, locale=mocker.sentinel.locale),
        mocker.call(number, locale="tr-TR"),
    ]
