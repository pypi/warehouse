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

import json
import os.path

from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid.path import AssetResolver
from pyramid.tweens import INGRESS, EXCVIEW
from pyramid.response import FileResponse
from webob.multidict import MultiDict
from whitenoise import WhiteNoise as _WhiteNoise


resolver = AssetResolver()


class WhiteNoise(_WhiteNoise):

    config_attrs = _WhiteNoise.config_attrs + ("manifest",)

    def __init__(self, *args, manifest=None, **kwargs):
        self.manifest_path = (
            resolver.resolve(manifest).abspath()
            if manifest is not None else None
        )
        return super().__init__(*args, **kwargs)

    @property
    def manifest(self):
        if not hasattr(self, "_manifest"):
            manifest_files = set()

            if self.manifest_path is not None:
                with open(self.manifest_path, "r", encoding="utf8") as fp:
                    data = json.load(fp)
                manifest_files.update(data.values())

            if not self.autorefresh:
                self._manifest = manifest_files

            return manifest_files
        else:
            return self._manifest

    def is_immutable_file(self, path, url):
        if self.manifest_path is not None:
            manifest_dir = os.path.dirname(self.manifest_path)
            if os.path.commonpath([self.manifest_path, path]) == manifest_dir:
                if os.path.relpath(path, manifest_dir) in self.manifest:
                    return True

        return super().is_immutable_file(path, url)


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
