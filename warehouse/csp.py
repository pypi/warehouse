import collections
import copy


def _serialize(policy):
    return "; ".join([
        " ".join([k] + [v2 for v2 in v if v2 is not None])
        for k, v in sorted(policy.items())
        if [v2 for v2 in v if v2 is not None]
    ])


def content_security_policy_tween_factory(handler, registry):
    def content_security_policy_tween(request):
        resp = handler(request)

        try:
            policy = request.find_service(name="csp")
        except ValueError:
            policy = collections.defaultdict(list)

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
    config.add_settings({
        "csp": {
            "connect-src": ["'self'"],
            "default-src": ["'none'"],
            "font-src": ["'self'", "fonts.gstatic.com"],
            "frame-ancestors": ["'none'"],
            "img-src": [
                "'self'",
                config.registry.settings["camo.url"],
                "https://secure.gravatar.com",
            ],
            "referrer": ["origin-when-cross-origin"],
            "reflected-xss": ["block"],
            "script-src": ["'self'"],
            "style-src": ["'self'", "fonts.googleapis.com"],
        },
    })
    config.add_tween("warehouse.csp.content_security_policy_tween_factory")
