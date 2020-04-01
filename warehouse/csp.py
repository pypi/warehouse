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

import collections
import copy

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

        # We don't want to apply our Content Security Policy to the debug
        # toolbar, that's not part of our application and it doesn't work with
        # our restrictive CSP.
        policy = _serialize(policy).format(request=request)
        if not request.path.startswith("/_debug_toolbar/") and policy:
            resp.headers["Content-Security-Policy"] = policy

        return resp

    return content_security_policy_tween


class CSPPolicy(collections.defaultdict):
    def __init__(self, policy=None):
        super().__init__(list, policy or {})

    def merge(self, policy):
        for key, attrs in policy.items():
            self[key].extend(attrs)


def csp_factory(_, request):
    try:
        return CSPPolicy(copy.deepcopy(request.registry.settings["csp"]))
    except KeyError:
        return CSPPolicy({})


def includeme(config):
    config.register_service_factory(csp_factory, name="csp")
    # Enable a Content Security Policy
    config.add_settings(
        {
            "csp": {
                "base-uri": [SELF],
                "block-all-mixed-content": [],
                "connect-src": [
                    SELF,
                    "https://api.github.com/repos/",
                    "*.fastly-insights.com",
                    "sentry.io",
                    "https://api.pwnedpasswords.com",
                ]
                + [
                    item
                    for item in [config.registry.settings.get("statuspage.url")]
                    if item
                ],
                "default-src": [NONE],
                "font-src": [SELF, "fonts.gstatic.com"],
                "form-action": [SELF],
                "frame-ancestors": [NONE],
                "frame-src": [NONE],
                "img-src": [
                    SELF,
                    config.registry.settings["camo.url"],
                    "www.google-analytics.com",
                    "*.fastly-insights.com",
                ],
                "script-src": [
                    SELF,
                    "www.googletagmanager.com",
                    "www.google-analytics.com",
                    "*.fastly-insights.com",
                    "https://cdn.ravenjs.com",
                ],
                "style-src": [SELF, "fonts.googleapis.com"],
                "worker-src": ["*.fastly-insights.com"],
            }
        }
    )
    config.add_tween("warehouse.csp.content_security_policy_tween_factory")
