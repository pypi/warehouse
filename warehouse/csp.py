# SPDX-License-Identifier: Apache-2.0

import collections
import copy

from urllib3.util import parse_url

from warehouse.config import Environment

SELF = "'self'"
NONE = "'none'"


def _serialize(policy):
    return "; ".join(
        [
            " ".join([k] + [v2 for v2 in v if v2 is not None])
            for k, v in sorted(policy.items())
        ]
    )


def content_security_policy_tween_factory(handler, registry):
    def content_security_policy_tween(request):
        resp = handler(request)

        try:
            policy = request.find_service(name="csp")
        except LookupError:
            policy = collections.defaultdict(list)

        # Replace CSP headers on /simple/ pages.
        if request.path.startswith("/simple/"):
            policy = collections.defaultdict(list)
            policy["sandbox"] = ["allow-top-navigation"]
            policy["default-src"] = [NONE]

        # Specific enables for Admin UI
        if request.path.startswith("/admin/"):
            policy["frame-src"] = ["https://inspector.pypi.io"]
            # Admin UI/Bootstrap 4 uses inline SVGs for icons
            policy["img-src"].extend(["data:"])
            # Link checking
            policy["connect-src"].extend([request.registry.settings["camo.url"]])

        # We don't want to apply our Content Security Policy to the debug
        # toolbar, that's not part of our application and it doesn't work with
        # our restrictive CSP.
        # We also want to exclude `/api/explorer` from the CSP, as it uses
        # `unsafe-eval` and `unsafe-inline` for the Swagger UI.
        policy = _serialize(policy).format(request=request)
        if (
            not request.path.startswith("/_debug_toolbar/")
            and not request.path.startswith("/api/explorer")
        ) and policy:
            resp.headers["Content-Security-Policy"] = policy

        return resp

    return content_security_policy_tween


class CSPPolicy(collections.defaultdict):
    def __init__(self, policy=None):
        super().__init__(list, policy or {})

    def merge(self, policy):
        for key, attrs in policy.items():
            self[key].extend(attrs)

            # The keyword 'none' must be the only source expression in the
            # directive value, otherwise it is ignored. If there's more than
            # one directive set, attempt to remove 'none' if it is present
            if NONE in self[key] and len(self[key]) > 1:
                self[key].remove(NONE)


def csp_factory(_, request):
    try:
        return CSPPolicy(copy.deepcopy(request.registry.settings["csp"]))
    except KeyError:
        return CSPPolicy({})


def _connect_src_settings(config) -> list:
    settings = [
        SELF,
        "https://api.github.com/repos/",
        "https://api.github.com/search/issues",
        "https://gitlab.com/api/",
        "https://analytics.python.org",
        "fastly-insights.com",
        "*.fastly-insights.com",
        "*.ethicalads.io",
        "https://api.pwnedpasswords.com",
        # Scoped deeply to prevent other scripts calling other CDN resources
        "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/sre/mathmaps/",
    ]

    settings.extend(
        [item for item in [config.registry.settings.get("statuspage.url")] if item]
    )

    if config.registry.settings.get("warehouse.env") == Environment.development:
        livereload_url = config.registry.settings.get("livereload.url")
        parsed_url = parse_url(livereload_url)

        # Incoming scheme could be http or https.
        scheme_replacement = "wss" if parsed_url.scheme == "https" else "ws"

        replaced = parsed_url._replace(scheme=scheme_replacement)  # noqa

        settings.extend(
            [
                f"{replaced.url}/livereload",
            ]
        )

    return settings


def _script_src_settings(config) -> list:
    settings = [
        SELF,
        "https://analytics.python.org",
        "*.fastly-insights.com",
        "*.ethicalads.io",
        "https://donate.python.org",
        # Hash for v1.4.0 of ethicalads.min.js
        "'sha256-U3hKDidudIaxBDEzwGJApJgPEf2mWk6cfMWghrAa6i0='",
        "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/",
        # Hash for v3.2.2 of MathJax tex-svg.js
        "'sha256-1CldwzdEg2k1wTmf7s5RWVd7NMXI/7nxxjJM2C4DqII='",
        # Hash for MathJax inline config
        # See warehouse/templates/packaging/detail.html
        "'sha256-0POaN8stWYQxhzjKS+/eOfbbJ/u4YHO5ZagJvLpMypo='",
    ]

    if config.registry.settings.get("warehouse.env") == Environment.development:
        settings.extend(
            [
                f"{config.registry.settings['livereload.url']}/livereload.js",
            ]
        )

    return settings


def includeme(config):
    config.register_service_factory(csp_factory, name="csp")
    # Enable a Content Security Policy
    config.add_settings(
        {
            "csp": {
                "base-uri": [SELF],
                "connect-src": _connect_src_settings(config),
                "default-src": [NONE],
                "font-src": [SELF, "fonts.gstatic.com"],
                "form-action": [
                    SELF,
                    "https://checkout.stripe.com",
                    "https://billing.stripe.com",
                ],
                "frame-ancestors": [NONE],
                "frame-src": [NONE],
                "img-src": [
                    SELF,
                    config.registry.settings["camo.url"],
                    "*.fastly-insights.com",
                    "*.ethicalads.io",
                    "ethicalads.blob.core.windows.net",
                ],
                "script-src": _script_src_settings(config),
                "style-src": [
                    SELF,
                    "fonts.googleapis.com",
                    "*.ethicalads.io",
                    "donate.python.org",
                    # Hashes for inline styles generated by v1.4.0 of ethicalads.min.js
                    "'sha256-2YHqZokjiizkHi1Zt+6ar0XJ0OeEy/egBnlm+MDMtrM='",
                    "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='",
                    # Hashes for inline styles generated by v3.2.2 of MathJax tex-svg.js
                    "'sha256-JLEjeN9e5dGsz5475WyRaoA4eQOdNPxDIeUhclnJDCE='",
                    "'sha256-mQyxHEuwZJqpxCw3SLmc4YOySNKXunyu2Oiz1r3/wAE='",
                    "'sha256-OCf+kv5Asiwp++8PIevKBYSgnNLNUZvxAp4a7wMLuKA='",
                    "'sha256-h5LOiLhk6wiJrGsG5ItM0KimwzWQH/yAcmoJDJL//bY='",
                ],
                "worker-src": ["*.fastly-insights.com"],
            }
        }
    )
    config.add_tween("warehouse.csp.content_security_policy_tween_factory")
