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

from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid.path import AssetResolver
from pyramid.tweens import INGRESS, EXCVIEW
from pyramid.response import FileResponse
from webob.multidict import MultiDict
from whitenoise import WhiteNoise


resolver = AssetResolver()


def whitenoise_tween_factory(handler, registry):

    def whitenoise_tween(request):
        whn = request.registry.whitenoise

        if whn.autorefresh:
            static_file = whn.find_file(request.path_info)
        else:
            static_file = whn.files.get(request.path_info)

        # We could not find a static file, so we'll just continue processing
        # this as normal.
        if static_file is None:
            return handler(request)

        request_headers = dict(kv for kv in request.environ.items()
                               if kv[0].startswith("HTTP_"))

        if request.method not in {"GET", "HEAD"}:
            return HTTPMethodNotAllowed()
        else:
            path, headers = static_file.get_path_and_headers(request_headers)
            headers = MultiDict(headers)

            resp = FileResponse(
                path,
                request=request,
                content_type=headers.pop("Content-Type", None),
                content_encoding=headers.pop("Content-Encoding", None),
            )
            resp.md5_etag()
            resp.headers.update(headers)

            return resp

    return whitenoise_tween


def whitenoise_serve_static(config, **kwargs):
    unsupported = kwargs.keys() - set(WhiteNoise.config_attrs)
    if unsupported:
        raise TypeError(
            "Unexpected keyword arguments: {!r}".format(unsupported))

    def register():
        config.registry.whitenoise = WhiteNoise(None, **kwargs)

    config.action(("whitenoise", "create instance"), register)


def whitenoise_add_files(config, path, prefix=None):
    def add_files():
        config.registry.whitenoise.add_files(
            resolver.resolve(path).abspath(),
            prefix=prefix,
        )

    config.action(("whitenoise", "add files", path, prefix), add_files)


def includeme(config):
    config.add_directive("whitenoise_serve_static", whitenoise_serve_static)
    config.add_directive("whitenoise_add_files", whitenoise_add_files)
    config.add_tween(
        "warehouse.static.whitenoise_tween_factory",
        over=[
            "warehouse.utils.compression.compression_tween_factory",
            EXCVIEW,
        ],
        under=[
            "warehouse.csp.content_security_policy_tween_factory",
            "warehouse.config.require_https_tween_factory",
            INGRESS,
        ],
    )
