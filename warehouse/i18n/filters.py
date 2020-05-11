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

import email.utils

import babel.dates
import babel.numbers
import jinja2

from pyramid.threadlocal import get_current_request


@jinja2.contextfilter
def format_date(ctx, *args, **kwargs):
    request = ctx.get("request") or get_current_request()
    kwargs.setdefault("locale", request.locale["code"])
    return babel.dates.format_date(*args, **kwargs)


@jinja2.contextfilter
def format_datetime(ctx, *args, **kwargs):
    request = ctx.get("request") or get_current_request()
    kwargs.setdefault("locale", request.locale["code"])
    return babel.dates.format_datetime(*args, **kwargs)


@jinja2.contextfilter
def format_rfc822_datetime(ctx, dt, *args, **kwargs):
    return email.utils.formatdate(dt.timestamp(), usegmt=True)


@jinja2.contextfilter
def format_number(ctx, number, locale=None):
    request = ctx.get("request") or get_current_request()
    if locale is None:
        locale = request.locale["code"]
    return babel.numbers.format_number(number, locale=locale)
