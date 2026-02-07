# SPDX-License-Identifier: Apache-2.0

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
