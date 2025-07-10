# SPDX-License-Identifier: Apache-2.0

import datetime
import functools
import re
import xmlrpc.client
import xmlrpc.server

from collections.abc import Mapping
from inspect import signature

from packaging.utils import canonicalize_name
from pydantic import StrictBool, StrictInt, StrictStr, ValidationError, validate_call
from pyramid.httpexceptions import HTTPMethodNotAllowed, HTTPTooManyRequests
from pyramid.view import view_config
from pyramid_rpc.mapper import MapplyViewMapper
from pyramid_rpc.xmlrpc import (
    XmlRpcApplicationError,
    XmlRpcError,
    XmlRpcInvalidMethodParams,
    exception_view as _exception_view,
    xmlrpc_method as _xmlrpc_method,
)
from sqlalchemy import func, select

from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.metrics import IMetricsService
from warehouse.packaging.models import (
    JournalEntry,
    Project,
    Release,
    ReleaseClassifiers,
    Role,
)
from warehouse.rate_limiting import IRateLimiter

# From https://stackoverflow.com/a/22273639
_illegal_ranges = [
    "\x00-\x08",
    "\x0b-\x0c",
    "\x0e-\x1f",
    "\x7f-\x84",
    "\x86-\x9f",
    "\ufdd0-\ufddf",
    "\ufffe-\uffff",
    "\U0001fffe-\U0001ffff",
    "\U0002fffe-\U0002ffff",
    "\U0003fffe-\U0003ffff",
    "\U0004fffe-\U0004ffff",
    "\U0005fffe-\U0005ffff",
    "\U0006fffe-\U0006ffff",
    "\U0007fffe-\U0007ffff",
    "\U0008fffe-\U0008ffff",
    "\U0009fffe-\U0009ffff",
    "\U000afffe-\U000affff",
    "\U000bfffe-\U000bffff",
    "\U000cfffe-\U000cffff",
    "\U000dfffe-\U000dffff",
    "\U000efffe-\U000effff",
    "\U000ffffe-\U000fffff",
    "\U0010fffe-\U0010ffff",
]
_illegal_xml_chars_re = re.compile("[%s]" % "".join(_illegal_ranges))

XMLRPC_DEPRECATION_URL = (
    "https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods"
)


def _clean_for_xml(data):
    """Sanitize any user-submitted data to ensure that it can be used in XML"""

    # If data is None or an empty string, don't bother
    if data:
        # This turns a string like "Hello…" into "Hello&#8230;"
        data = data.encode("ascii", "xmlcharrefreplace").decode("ascii")
        # However it's still possible that there are invalid characters in the string,
        # so simply remove any of those characters
        return _illegal_xml_chars_re.sub("", data)
    return data


def submit_xmlrpc_metrics(method=None):
    """
    Submit metrics.
    """

    def decorator(f):
        def wrapped(context, request):
            metrics = request.find_service(IMetricsService, context=None)
            metrics.increment("warehouse.xmlrpc.call", tags=[f"rpc_method:{method}"])
            with metrics.timed(
                "warehouse.xmlrpc.timing", tags=[f"rpc_method:{method}"]
            ):
                return f(context, request)

        return wrapped

    return decorator


def ratelimit():
    def decorator(f):
        def wrapped(context, request):
            ratelimiter = request.find_service(
                IRateLimiter, name="xmlrpc.client", context=None
            )
            metrics = request.find_service(IMetricsService, context=None)
            ratelimiter.hit(request.remote_addr)
            if not ratelimiter.test(request.remote_addr):
                metrics.increment("warehouse.xmlrpc.ratelimiter.exceeded", tags=[])
                message = (
                    "The action could not be performed because there were too "
                    "many requests by the client."
                )
                _resets_in = ratelimiter.resets_in(request.remote_addr)
                if _resets_in is not None:
                    _resets_in = max(1, int(_resets_in.total_seconds()))
                    message += f" Limit may reset in {_resets_in} seconds."
                raise XMLRPCWrappedError(HTTPTooManyRequests(message))
            metrics.increment("warehouse.xmlrpc.ratelimiter.hit", tags=[])
            return f(context, request)

        return wrapped

    return decorator


def xmlrpc_method(**kwargs):
    """
    Support multiple endpoints serving the same views by chaining calls to
    xmlrpc_method
    """
    # Add some default arguments
    kwargs.update(
        require_csrf=False,
        require_methods=["POST"],
        decorator=(submit_xmlrpc_metrics(method=kwargs["method"]), ratelimit()),
        mapper=TypedMapplyViewMapper,
    )

    def decorator(f):
        rpc2 = _xmlrpc_method(endpoint="xmlrpc.RPC2", **kwargs)
        pypi = _xmlrpc_method(endpoint="xmlrpc.pypi", **kwargs)
        pypi_slash = _xmlrpc_method(endpoint="xmlrpc.pypi_slash", **kwargs)
        return rpc2(pypi_slash(pypi(f)))

    return decorator


xmlrpc_cache_by_project = functools.partial(
    xmlrpc_method,
    xmlrpc_cache=True,
    xmlrpc_cache_expires=48 * 60 * 60,  # 48 hours
    xmlrpc_cache_tag="project/%s",
    xmlrpc_cache_arg_index=0,
    xmlrpc_cache_tag_processor=canonicalize_name,
)


xmlrpc_cache_all_projects = functools.partial(
    xmlrpc_method,
    xmlrpc_cache=True,
    xmlrpc_cache_expires=1 * 60 * 60,  # 1 hours
    xmlrpc_cache_tag="all-projects",
)


class XMLRPCServiceUnavailable(XmlRpcError):
    # NOQA due to N815 'mixedCase variable in class scope',
    # This is the interface for specifying fault code and string for XmlRpcError
    faultCode = -32403  # NOQA: ignore=N815
    faultString = "server error; service unavailable"  # NOQA: ignore=N815


class XMLRPCInvalidParamTypes(XmlRpcInvalidMethodParams):
    def __init__(self, exc):
        self.exc = exc

    # NOQA due to N802 'function name should be lowercase'
    # This is the interface for specifying fault string for XmlRpcError
    @property
    def faultString(self):  # NOQA: ignore=N802
        return f"client error; {self.exc}"


class XMLRPCWrappedError(xmlrpc.client.Fault):
    def __init__(self, exc):
        # NOQA due to N815 'mixedCase variable in class scope',
        # This is the interface for specifying fault code and string for XmlRpcError
        self.faultCode = -32500  # NOQA: ignore=N815
        self.wrapped_exception = exc  # NOQA: ignore=N815

    # NOQA due to N802 'function name should be lowercase'
    # This is the interface for specifying fault string for XmlRpcError
    @property
    def faultString(self):  # NOQA: ignore=N802
        return "{exc.__class__.__name__}: {exc}".format(exc=self.wrapped_exception)


class TypedMapplyViewMapper(MapplyViewMapper):
    def mapply(self, fn, args, kwargs):
        try:
            return validate_call(fn)(*args, **kwargs)
        except ValidationError as exc:
            raise XMLRPCInvalidParamTypes(
                "; ".join(
                    [
                        (
                            list(signature(fn).parameters.keys())[e["loc"][0]]
                            if isinstance(e["loc"][0], int)
                            and e["loc"][0] < len(signature(fn).parameters.keys())
                            else str(e["loc"][0])
                        )
                        + ": "
                        + e["msg"]
                        for e in exc.errors()
                    ]
                )
            )


@view_config(route_name="xmlrpc.pypi", context=Exception, renderer="xmlrpc")
def exception_view(exc, request):
    if isinstance(exc, HTTPMethodNotAllowed):
        return XmlRpcApplicationError()
    return _exception_view(exc, request)


# Mirroring Support


@xmlrpc_method(method="changelog_last_serial")
def changelog_last_serial(request):
    return request.db.query(func.max(JournalEntry.id)).scalar()


@xmlrpc_method(method="changelog_since_serial")
def changelog_since_serial(request, serial: StrictInt):
    entries = (
        request.db.query(JournalEntry)
        .filter(JournalEntry.id > serial)
        .order_by(JournalEntry.id)
        .limit(50000)
    )

    return [
        (
            e.name,
            e.version,
            int(e.submitted_date.replace(tzinfo=datetime.UTC).timestamp()),
            _clean_for_xml(e.action),
            e.id,
        )
        for e in entries
    ]


@xmlrpc_cache_all_projects(method="list_packages_with_serial")
def list_packages_with_serial(request):
    # Have PostgreSQL create the dictionary directly
    query = select(
        func.jsonb_object_agg(Project.name, Project.last_serial).label(
            "package_serials"
        )
    )

    result = request.db.execute(query).scalar()
    return result or {}


# Package querying methods


@xmlrpc_cache_by_project(method="package_roles")
def package_roles(request, package_name: StrictStr):
    roles = (
        request.db.query(Role)
        .join(User)
        .join(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(package_name))
        .order_by(Role.role_name.desc(), User.username)
        .all()
    )
    return [(r.role_name, r.user.username) for r in roles]


@xmlrpc_method(method="user_packages")
def user_packages(request, username: StrictStr):
    roles = (
        request.db.query(Role)
        .join(User)
        .join(Project)
        .filter(User.username == username)
        .order_by(Role.role_name.desc(), Project.name)
        .all()
    )
    return [(r.role_name, r.project.name) for r in roles]


@xmlrpc_method(method="browse")
def browse(request, classifiers: list[StrictStr]):
    classifiers_q = (
        request.db.query(Classifier)
        .filter(Classifier.classifier.in_(classifiers))
        .subquery()
    )

    release_classifiers_q = (
        select(ReleaseClassifiers)
        .where(ReleaseClassifiers.trove_id == classifiers_q.c.id)
        .alias("rc")
    )

    releases = (
        request.db.query(Project.name, Release.version)
        .join(Release)
        .join(release_classifiers_q, Release.id == release_classifiers_q.c.release_id)
        .group_by(Project.name, Release.version)
        .having(func.count() == len(classifiers))
        .order_by(Project.name, Release.version)
        .all()
    )

    return [(r.name, r.version) for r in releases]


# Synthetic methods


@xmlrpc_method(method="system.multicall")
def multicall(request, args):
    raise XMLRPCWrappedError(
        ValueError(
            "MultiCall requests have been deprecated, use individual "
            "requests instead."
        )
    )


# Deprecated Methods


@xmlrpc_method(method="changelog")
def changelog(request, since: StrictInt, with_ids: StrictBool = False):
    raise XMLRPCWrappedError(
        ValueError(
            "The changelog method has been deprecated, use changelog_since_serial "
            "instead."
        )
    )


@xmlrpc_method(method="package_data")
def package_data(request, package_name, version):
    raise XMLRPCWrappedError(
        RuntimeError(
            "This API has been deprecated. "
            f"See {XMLRPC_DEPRECATION_URL} for more information."
        )
    )


@xmlrpc_method(method="package_urls")
def package_urls(request, package_name, version):
    raise XMLRPCWrappedError(
        RuntimeError(
            "This API has been deprecated. "
            f"See {XMLRPC_DEPRECATION_URL} for more information."
        )
    )


@xmlrpc_method(method="top_packages")
def top_packages(request, num: StrictInt | None = None):
    raise XMLRPCWrappedError(
        RuntimeError(
            "This API has been removed. Use BigQuery instead. "
            f"See {XMLRPC_DEPRECATION_URL} for more information."
        )
    )


@xmlrpc_method(method="search")
def search(
    request,
    spec: Mapping[StrictStr, StrictStr | list[StrictStr]],
    operator: StrictStr = "and",
):
    domain = request.registry.settings.get("warehouse.domain", request.domain)
    raise XMLRPCWrappedError(
        RuntimeError(
            "PyPI no longer supports 'pip search' (or XML-RPC search). "
            f"Please use https://{domain}/search (via a browser) instead. "
            f"See {XMLRPC_DEPRECATION_URL} for more information."
        )
    )


@xmlrpc_method(method="list_packages")
def list_packages(request):
    raise XMLRPCWrappedError(
        RuntimeError(
            "PyPI no longer supports the XMLRPC list_packages method. "
            "Use Simple API instead. "
            f"See {XMLRPC_DEPRECATION_URL} "
            "for more information."
        )
    )


@xmlrpc_method(method="package_releases")
def package_releases(request, package_name: StrictStr, show_hidden: StrictBool = False):
    raise XMLRPCWrappedError(
        RuntimeError(
            "PyPI no longer supports the XMLRPC package_releases method. "
            "Use JSON or Simple API instead. "
            f"See {XMLRPC_DEPRECATION_URL} "
            "for more information."
        )
    )


@xmlrpc_method(method="release_urls")
def release_urls(request, package_name: StrictStr, version: StrictStr):
    raise XMLRPCWrappedError(
        RuntimeError(
            "PyPI no longer supports the XMLRPC release_urls method. "
            "Use JSON or Simple API instead. "
            f"See {XMLRPC_DEPRECATION_URL} "
            "for more information."
        )
    )


@xmlrpc_method(method="release_data")
def release_data(request, package_name: StrictStr, version: StrictStr):
    raise XMLRPCWrappedError(
        RuntimeError(
            "PyPI no longer supports the XMLRPC release_data method. "
            "Use JSON or Simple API instead. "
            f"See {XMLRPC_DEPRECATION_URL} "
            "for more information."
        )
    )
