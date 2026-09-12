# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import (
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
)
from warehouse.accounts.models import User
from warehouse.cache import origin
from warehouse.cache.origin.derivers import html_cache_deriver
from warehouse.cache.origin.interfaces import IOriginCache
from warehouse.observations.models import ObservationKind


def test_store_purge_keys(mocker):
    class Type1:
        pass

    class Type2:
        pass

    class Type3:
        pass

    class Type4:
        pass

    # Type5 is registered but produces empty purge keys (covers if keys: falsy)
    class Type5:
        pass

    config = types.SimpleNamespace(
        registry={
            "cache_keys": {
                Type1: lambda o: origin.CacheKeys(cache=[], purge=["type_1"]),
                Type2: lambda o: origin.CacheKeys(cache=[], purge=["type_2", "foo"]),
                Type3: lambda o: origin.CacheKeys(cache=[], purge=["type_3", "foo"]),
                Type5: lambda o: origin.CacheKeys(cache=[], purge=[]),
            }
        }
    )
    session = types.SimpleNamespace(
        info={},
        new={Type1(), Type5()},
        dirty={Type2()},
        deleted={Type3(), Type4()},
    )

    origin.store_purge_keys(config, session, mocker.sentinel.flush_context)

    assert session.info["warehouse.cache.origin.purges"] == {
        "type_1",
        "type_2",
        "type_3",
        "foo",
    }


def test_store_purge_keys_dirty_with_changed_attrs(app_config, db_session):
    project = ProjectFactory.create()
    # Dirty the project by changing a column
    project.lifecycle_status = "quarantine-enter"
    # Flush so the object lands in session.dirty for the after_flush listener
    db_session.flush()

    purges = db_session.info.get("warehouse.cache.origin.purges", set())

    assert f"project/{project.normalized_name}" in purges


def _trigger_event(project, request):
    project.record_event(tag="test:event", request=request, additional={})


def _trigger_observation(project, request):
    project.record_observation(
        request=request,
        kind=ObservationKind.IsMalware,
        actor=UserFactory.create(),
        summary="test",
        payload={},
    )


def _trigger_invitation(project, request):
    RoleInvitationFactory.create(project=project)


@pytest.mark.parametrize(
    "trigger",
    [_trigger_event, _trigger_observation, _trigger_invitation],
    ids=["events", "observations", "invitations"],
)
def test_store_purge_keys_skips_audit_only_collection_changes(
    trigger, app_config, db_request
):
    # Audit/admin-only collection mutations (events, observations, invitations)
    # never affect publicly-cached content and should not trigger a Project purge.
    project = ProjectFactory.create()
    db_request.db.flush()
    db_request.db.info.pop("warehouse.cache.origin.purges", None)

    trigger(project, db_request)
    db_request.db.flush()

    purges = db_request.db.info.get("warehouse.cache.origin.purges", set())
    assert f"project/{project.normalized_name}" not in purges


def test_store_purge_keys_skips_project_dirty_on_roles_change(app_config, db_request):
    # Role has its own cache_keys; the Project-dirty purge would only add
    # all-projects and org/{name}, which aren't affected by role membership.
    project = ProjectFactory.create()
    db_request.db.flush()
    db_request.db.info.pop("warehouse.cache.origin.purges", None)

    role = RoleFactory.create(project=project)
    db_request.db.flush()

    purges = db_request.db.info.get("warehouse.cache.origin.purges", set())
    assert f"project/{project.normalized_name}" in purges
    assert f"user/{role.user.username}" in purges
    assert "all-projects" not in purges


def test_store_purge_keys_skips_release_dirty_on_files_change(app_config, db_request):
    # File has its own cache_keys (project/{name}); Release-dirty would only
    # add user/*, all-projects, org/{name}, none of which are affected by a
    # file change to an existing release.
    release = ReleaseFactory.create()
    db_request.db.flush()
    db_request.db.info.pop("warehouse.cache.origin.purges", None)

    FileFactory.create(release=release)
    db_request.db.flush()

    purges = db_request.db.info.get("warehouse.cache.origin.purges", set())
    assert f"project/{release.project.normalized_name}" in purges
    assert "all-projects" not in purges


def test_store_purge_keys_skips_project_dirty_on_releases_change(
    app_config, db_request, mocker
):
    # Release's cache_keys emit the SAME 4 keys as Project's would, so the
    # purge set can't distinguish; assert via log emissions instead.
    log_info = mocker.spy(origin.logger, "info")

    project = ProjectFactory.create()
    db_request.db.flush()
    log_info.reset_mock()

    ReleaseFactory.create(project=project)
    db_request.db.flush()

    purge_logs = [
        call
        for call in log_info.call_args_list
        if call.args and call.args[0] == "cache_purge_keys_generated"
    ]
    logged_classes = {
        (call.kwargs.get("obj_class"), call.kwargs.get("state")) for call in purge_logs
    }
    assert ("Release", "new") in logged_classes
    assert ("Project", "dirty") not in logged_classes


def test_execute_purge_success(app_config, mocker):
    cacher = mocker.Mock(spec=["purge"])
    factory = mocker.Mock(return_value=cacher)
    mocker.patch.object(
        app_config, "find_service_factory", autospec=True, return_value=factory
    )
    session = types.SimpleNamespace(
        info={"warehouse.cache.origin.purges": {"type_1", "type_2", "foobar"}}
    )

    origin.execute_purge(app_config, session)

    factory.assert_called_once_with(None, app_config)
    cacher.purge.assert_called_once_with({"type_1", "type_2", "foobar"})
    assert "warehouse.cache.origin.purges" not in session.info


def test_execute_purge_empty(app_config, db_session):
    # No purges key in session.info — should early-return without touching cacher
    origin.execute_purge(app_config, db_session)

    assert "warehouse.cache.origin.purges" not in db_session.info


def test_execute_purge_no_backend(app_config, mocker):
    find_service_factory = mocker.patch.object(
        app_config, "find_service_factory", autospec=True, side_effect=LookupError
    )
    session = types.SimpleNamespace(
        info={"warehouse.cache.origin.purges": {"type_1", "type_2", "foobar"}}
    )

    origin.execute_purge(app_config, session)

    find_service_factory.assert_called_once_with(origin.IOriginCache)
    assert "warehouse.cache.origin.purges" not in session.info


class TestOriginCache:
    def test_no_cache_key(self, pyramid_request, mocker):
        response = mocker.sentinel.response

        @origin.origin_cache(1)
        def view(context, request):
            return response

        # IOriginCache is unregistered, so the real find_service raises LookupError
        pyramid_request.registry["cache_keys"] = {}
        context = mocker.sentinel.context

        assert view(context, pyramid_request) is response

    def test_no_origin_cache(self, pyramid_request, mocker):
        class Fake:
            pass

        response = mocker.sentinel.response

        @origin.origin_cache(1)
        def view(context, request):
            return response

        context = Fake()
        pyramid_request.registry["cache_keys"] = {
            Fake: lambda X: origin.CacheKeys(cache=[], purge=[])  # noqa: N803
        }
        # IOriginCache is unregistered, so the real find_service raises LookupError
        find_service = mocker.spy(pyramid_request, "find_service")

        assert view(context, pyramid_request) is response
        find_service.assert_called_once_with(IOriginCache)

    @pytest.mark.parametrize(("seconds", "keys"), [(745, None), (823, ["nope", "yup"])])
    def test_response_hook(self, seconds, keys, pyramid_request, mocker):
        class Fake:
            pass

        response = mocker.sentinel.response
        cacher = mocker.Mock(spec=["cache"])

        deco = origin.origin_cache(seconds, keys=keys)

        @deco
        def view(context, request):
            return response

        key_maker = mocker.Mock(
            return_value=origin.CacheKeys(cache=["one", "two"], purge=[])
        )
        context = Fake()
        pyramid_request.registry["cache_keys"] = {Fake: key_maker}
        mocker.patch.object(pyramid_request, "find_service", return_value=cacher)

        assert view(context, pyramid_request) is response
        key_maker.assert_called_once_with(context)
        assert len(pyramid_request.response_callbacks) == 1

        pyramid_request.response_callbacks[0](pyramid_request, response)

        cacher.cache.assert_called_once_with(
            ["one", "two"] + ([] if keys is None else keys),
            pyramid_request,
            response,
            seconds=seconds,
            stale_while_revalidate=None,
            stale_if_error=None,
        )


class TestKeyMaker:
    def test_both_cache_and_purge(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo", "foo/{obj.attr}"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{obj.attr}"),
            ],
        )
        cache_keys = key_maker(types.SimpleNamespace(attr="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo", "foo/bar"]
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_only_cache(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo", "foo/{obj.attr}"], purge_keys=None
        )
        cache_keys = key_maker(types.SimpleNamespace(attr="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo", "foo/bar"]
        assert list(cache_keys.purge) == []

    def test_only_purge(self):
        key_maker = origin.key_maker_factory(
            cache_keys=None,
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{obj.attr}"),
            ],
        )
        cache_keys = key_maker(types.SimpleNamespace(attr="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == []
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_iterate_on(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],  # Intentionally does not support `iterate_on`
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{itr}", iterate_on="iterate_me"),
            ],
        )
        cache_keys = key_maker(types.SimpleNamespace(iterate_me=["biz", "baz"]))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar", "bar/biz", "bar/baz"]

    def test_if_attr_exists_exists(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo"),
            ],
        )
        cache_keys = key_maker(types.SimpleNamespace(foo="bar"))

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_if_attr_exists_nested(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo.bar"),
            ],
        )
        cache_keys = key_maker(
            types.SimpleNamespace(foo=types.SimpleNamespace(bar="bar"))
        )

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar", "bar/bar"]

    def test_if_attr_exists_does_not_exist(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo"),
            ],
        )
        cache_keys = key_maker(types.SimpleNamespace())

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar"]

    def test_if_attr_exists_nested_does_not_exist(self):
        key_maker = origin.key_maker_factory(
            cache_keys=["foo"],
            purge_keys=[
                origin.key_factory("bar"),
                origin.key_factory("bar/{attr}", if_attr_exists="foo.bar"),
            ],
        )
        cache_keys = key_maker(types.SimpleNamespace())

        assert isinstance(cache_keys, origin.CacheKeys)
        assert cache_keys.cache == ["foo"]
        assert list(cache_keys.purge) == ["bar"]


class TestReceiveSet:
    def test_with_purge_keys(self, app_config, db_session):
        user = UserFactory.create()
        # User.name is registered with purge_keys in packaging/__init__.py.
        # Trigger the attribute set listener by changing the user's name.
        origin.receive_set(User.name, app_config, user)

        purges = db_session.info.get("warehouse.cache.origin.purges", set())
        assert f"user/{user.username}" in purges


def test_register_origin_keys(mocker):
    class Fake1:
        pass

    class Fake2:
        pass

    key_maker = mocker.sentinel.key_maker
    key_maker_factory = mocker.patch.object(
        origin, "key_maker_factory", autospec=True, return_value=key_maker
    )

    config = types.SimpleNamespace(registry={})

    origin.register_origin_cache_keys(
        config, Fake1, cache_keys=["one", "two/{obj.attr}"]
    )
    origin.register_origin_cache_keys(
        config, Fake2, cache_keys=["three"], purge_keys=["lol"]
    )

    assert key_maker_factory.call_args_list == [
        mocker.call(cache_keys=["one", "two/{obj.attr}"], purge_keys=None),
        mocker.call(cache_keys=["three"], purge_keys=["lol"]),
    ]
    assert config.registry == {"cache_keys": {Fake1: key_maker, Fake2: key_maker}}


def test_includeme_no_origin_cache(mocker):
    config = mocker.Mock(spec=["add_directive", "registry"])
    config.registry.settings = {}

    origin.includeme(config)

    config.add_directive.assert_called_once_with(
        "register_origin_cache_keys", origin.register_origin_cache_keys
    )


def test_includeme_with_origin_cache(mocker):
    cache_class = mocker.Mock(spec=["create_service"])
    config = mocker.Mock(
        spec=[
            "add_directive",
            "add_view_deriver",
            "maybe_dotted",
            "register_service_factory",
            "registry",
        ]
    )
    config.registry.settings = {
        "origin_cache.backend": "warehouse.cache.origin.fastly.FastlyCache"
    }
    config.maybe_dotted.return_value = cache_class

    origin.includeme(config)

    config.add_directive.assert_called_once_with(
        "register_origin_cache_keys", origin.register_origin_cache_keys
    )
    config.add_view_deriver.assert_called_once_with(html_cache_deriver)
    config.maybe_dotted.assert_called_once_with(
        "warehouse.cache.origin.fastly.FastlyCache"
    )
    config.register_service_factory.assert_called_once_with(
        cache_class.create_service, IOriginCache
    )
