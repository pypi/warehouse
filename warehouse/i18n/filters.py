# SPDX-License-Identifier: Apache-2.0

import email.utils

import babel.dates
import babel.numbers
import jinja2

from pyramid.threadlocal import get_current_request


@jinja2.pass_context
def format_date(ctx, *args, **kwargs):
    request = ctx.get("request") or get_current_request()
    kwargs.setdefault("locale", request.locale)
    return babel.dates.format_date(*args, **kwargs)


@jinja2.pass_context
def format_datetime(ctx, *args, **kwargs):
    request = ctx.get("request") or get_current_request()
    kwargs.setdefault("locale", request.locale)
    return babel.dates.format_datetime(*args, **kwargs)


@jinja2.pass_context
def format_rfc822_datetime(ctx, dt, *args, **kwargs):
    return email.utils.formatdate(dt.timestamp(), usegmt=True)


@jinja2.pass_context
def format_number(ctx, number, locale=None):
    request = ctx.get("request") or get_current_request()
    if locale is None:
        locale = request.locale
    return babel.numbers.format_decimal(number, locale=locale)
