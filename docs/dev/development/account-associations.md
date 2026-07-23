# Account Associations (OAuth backends)

Account associations let a PyPI user link their account
to a third-party identity provider (GitHub, GitLab) for identity verification.
The OAuth token is used only to confirm the external identity at link time;
it is **not** stored.
What gets stored is the provider name, the provider's stable numeric user ID,
and the username.

This is distinct from Trusted Publishing (OIDC, in `warehouse/oidc/`),
which authenticates CI/CD systems for uploads.
Account associations authenticate a human linking their own profile.

## Architecture

Each provider is an implementation of `IOAuthProviderService` (`warehouse/accounts/oauth.py`).
The concrete clients are:

| Provider | Real client | Null client (dev/test) | Flow |
| -------- | ----------- | ---------------------- | ---- |
| GitHub | `GitHubAppClient` | `NullGitHubOAuthClient` | GitHub App OAuth |
| GitLab | `GitLabOAuthClient` | `NullGitLabOAuthClient` | OAuth 2.0, `read_user` scope |

Services are registered per-provider in `warehouse/accounts/__init__.py`
via `register_service_factory(..., IOAuthProviderService, name="<provider>")`.
The views live in `warehouse/manage/views/account_associations.py`
and the `connect`/`callback` routes in `warehouse/routes.py`
(`/manage/account/associations/<provider>/{connect,callback}`).

The provider's numeric `id` is the stable identifier for linking -
usernames can change, IDs cannot.

## Configuration

Backends are selected by environment variable, parsed in `warehouse/config.py`
with `maybe_set_compound` into `<provider>.oauth.backend` settings:

| Env var | Setting | Required? |
| ------- | ------- | --------- |
| `GITHUB_OAUTH_BACKEND` | `github.oauth.backend` | **Required** - registered unconditionally |
| `GITLAB_OAUTH_BACKEND` | `gitlab.oauth.backend` | Optional - registered only when set; the views return 404 when unconfigured |

The value uses a compound format - the client class path
followed by space-separated `key=value` kwargs:

```bash
GITLAB_OAUTH_BACKEND=warehouse.accounts.oauth.GitLabOAuthClient client_id=<app-id> client_secret=<app-secret>
```

The real clients read `<provider>.oauth.client_id` and
`<provider>.oauth.client_secret` from settings in `create_service`.

### Local development

`dev/environment` already wires both providers to their Null clients,
so the account-associations UI works locally without registering real OAuth apps:

```bash
GITHUB_OAUTH_BACKEND=warehouse.accounts.oauth.NullGitHubOAuthClient
GITLAB_OAUTH_BACKEND=warehouse.accounts.oauth.NullGitLabOAuthClient
```

The Null clients simulate the OAuth round-trip and must never be used in
production.

## Gotcha: missing `client_id`/`client_secret`

Setting a backend to the real client class **without** the `client_id` and
`client_secret` kwargs is a footgun that passes startup and fails later:

```bash
# Broken - no kwargs
GITLAB_OAUTH_BACKEND=warehouse.accounts.oauth.GitLabOAuthClient
```

`includeme` only checks that the backend setting is present, so the app boots fine.
But `create_service` reads `settings["gitlab.oauth.client_id"]`,
so the first time a user clicks "Connect", the request 500s with `KeyError: 'gitlab.oauth.client_id'`.
Always pass both kwargs with the real client.
This applies to every provider.

## Adding a new provider

Follow the `GitLabOAuthClient` pattern:

1. Add the client class (and a `Null*Client`) in
   `warehouse/accounts/oauth.py`, implementing `IOAuthProviderService`.
2. Parse the backend env var in `warehouse/config.py` with `maybe_set_compound`.
3. Register the service factory in `warehouse/accounts/__init__.py`
   (gate it on the setting being present if the provider is optional).
4. Add `connect`/`callback` routes in `warehouse/routes.py` and views in
   `warehouse/manage/views/account_associations.py`.
5. Update the account-associations UI in `warehouse/templates/manage/account.html`.
6. Add tests in `tests/unit/accounts/test_oauth.py` and test config in `tests/conftest.py`.
