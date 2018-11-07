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


from pyramid.static import ManifestCacheBuster as _ManifestCacheBuster


class ManifestCacheBuster(_ManifestCacheBuster):
    def __init__(self, *args, strict=True, **kwargs):
        super().__init__(*args, **kwargs)

        self.strict = strict

    def __call__(self, request, subpath, kw):
        try:
            return self.manifest[subpath], kw
        except KeyError:
            # If we're not in strict mode, then we'll allow missing files to
            # just fall back to the un-cachebusted path.
            if not self.strict:
                return subpath, kw

            # We raise an error here even though the one from Pyramid does not.
            # This is done because we want to be strict that all static files
            # must be cache busted otherwise it is likely an error of some kind
            # and should be remedied and without a loud error it's unlikely to
            # be noticed.
            raise ValueError(
                "{} is not able to be cache busted.".format(subpath)
            ) from None
