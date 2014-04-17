# Copyright 2014 Donald Stufft
#
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
import functools
import string

from warehouse.utils import validate_and_normalize_package_name


class FastlyFormatter(string.Formatter):

    def convert_field(self, value, conversion):
        if conversion == "n":
            return validate_and_normalize_package_name(value)
        return super(FastlyFormatter, self).convert_field(value, conversion)


class FastlyKey:

    def __init__(self, *keys):
        self.keys = keys

    def __call__(self, fn=None, **names):
        def decorator(fn):
            @functools.wraps(fn)
            def wrapped(app, request, *args, **kwargs):
                # Get the response from the view
                resp = fn(app, request, *args, **kwargs)

                # Resolve our surrogate keys
                view_kwargs = {"app": app, "request": request}
                view_kwargs.update(kwargs)
                ctx = {
                    names.get(k, k): v
                    for k, v in view_kwargs.items()
                }

                # Set our Fastly Surrogate-Key header
                resp.headers["Surrogate-Key"] = " ".join(
                    self.format_keys(**ctx)
                )

                # Return the modified response
                return resp
            return wrapped

        if fn is not None:
            return decorator(fn)
        else:
            return decorator

    def format_keys(self, **context):
        return [
            FastlyFormatter().format(key, **context)
            for key in self.keys
        ]


projects = FastlyKey("project", "project/{project!n}")


users = FastlyKey("user", "user/{username!n}")


rss = FastlyKey("rss")
