# SPDX-License-Identifier: Apache-2.0

# Fixtures for ReadPermissionPostEscalation.ql
# Each labeled block exercises one branch of the query.


class Permissions:
    FooRead = "foo:read"
    FooWrite = "foo:write"
    FooManage = "foo:manage"


def view_config(**kwargs):
    def decorator(func):
        return func

    return decorator


def other_decorator(**kwargs):
    def decorator(func):
        return func

    return decorator


# --- POSITIVE: sub-pattern A -------------------------------------------------
# require_methods=False + read permission + body checks request.method == "POST"
@view_config(
    route_name="positive.subpattern_a",
    require_methods=False,
    permission=Permissions.FooRead,
)
def positive_a_require_methods_false_with_body_check(request):
    if request.method == "POST":
        return "handle post"
    return "show form"


# --- POSITIVE: sub-pattern B1 ------------------------------------------------
# require_methods=["POST"] + read permission
@view_config(
    route_name="positive.subpattern_b1",
    require_methods=["POST"],
    permission=Permissions.FooRead,
)
def positive_b1_require_methods_post_only(request):
    return "post action"


# --- POSITIVE: sub-pattern B2 ------------------------------------------------
# request_method="POST" + read permission
@view_config(
    route_name="positive.subpattern_b2",
    request_method="POST",
    permission=Permissions.FooRead,
)
def positive_b2_request_method_post(request):
    return "post action"


# --- NEGATIVE: explicit GET --------------------------------------------------
# request_method="GET" should exclude even if permission is read
@view_config(
    route_name="negative.explicit_get",
    request_method="GET",
    permission=Permissions.FooRead,
)
def negative_explicit_get(request):
    return "get action"


# --- NEGATIVE: POST with write permission -----------------------------------
@view_config(
    route_name="negative.post_write_perm",
    request_method="POST",
    permission=Permissions.FooWrite,
)
def negative_post_with_write_permission(request):
    return "post action"


# --- NEGATIVE: POST with manage permission (not *Read*) ---------------------
@view_config(
    route_name="negative.post_manage_perm",
    require_methods=["POST"],
    permission=Permissions.FooManage,
)
def negative_post_with_manage_permission(request):
    return "post action"


# --- NEGATIVE: sub-pattern A shape but body never checks request.method -----
@view_config(
    route_name="negative.no_body_check",
    require_methods=False,
    permission=Permissions.FooRead,
)
def negative_no_body_post_check(request):
    return "no post branch"


# --- NEGATIVE: not a view_config decorator ----------------------------------
@other_decorator(
    require_methods=["POST"],
    permission=Permissions.FooRead,
)
def negative_not_view_config(request):
    return "post action"
