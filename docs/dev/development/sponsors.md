# Sponsors

PyPI shows the logos of Python Software Foundation sponsors in the page
footer, on the [sponsors page](https://pypi.org/sponsors/) and in the sidebar
of project and organization pages. The data lives in the `sponsors` table and
is managed through the admin UI and the python.org sync described below.

## Syncing from python.org

`warehouse.sponsors.tasks.update_pypi_sponsors` runs hourly when
`pythondotorg.api_token` is set. It reads python.org's logo placement API
(`/api/v2/sponsors/logo-placement/`) for publisher `pypi` twice:

| Flight     | Sets                                     |
|------------|------------------------------------------|
| `sponsors` | `psf_sponsor`, `footer` (from the level) |
| `sidebar`  | `sidebar`                                |

Both flights create or update the sponsor row (name, slug, description, link,
logos, level) and mark it `origin = "remote"`. Before each run `psf_sponsor`
is cleared on every sponsor, and `footer` and `sidebar` are cleared on remote
sponsors, so a sponsor that leaves a flight stops showing there. Sponsors
flagged `infra_sponsor` or `one_time` are never updated from the API. The
`footer` and `sidebar` checkboxes in the admin are only authoritative for
sponsors with `origin = "manual"`; on remote sponsors the API wins on the next
run.

A sponsor that is only in the `sidebar` flight is created with
`psf_sponsor = False`, so it appears in the sidebar but not on the sponsors
page.

## Sidebar placement

`request.sponsors["sidebar"]` lists the active sponsors with the `sidebar`
flag. `warehouse/templates/includes/sidebar-sponsor-logo.html` renders all of
them, hidden, on project pages (except projects owned by a Company
organization) and on organization profiles. Those pages are cached at the CDN
for a day, so the choice of which sponsor to show is made in the browser by
`warehouse/static/js/warehouse/controllers/sponsor_controller.js`, which
reveals one at random. Without JavaScript nothing is shown. Changes to the
eligible set reach visitors as cached pages expire.

The project page contains the placement twice (desktop sidebar and the mobile
"Metadata" tab). The controller keeps the chosen sponsor and the impression
state at module level, so both copies show the same sponsor and one page view
counts once.

## Analytics

The controller reports to the PSF's Plausible instance at
<https://analytics.python.org> through `window.plausible`, which the base
template sets up. Events and properties:

| Event                | When                                                      | `interactive` |
|----------------------|-----------------------------------------------------------|---------------|
| `Sponsor Impression` | the placement is at least 50% visible, once per page view | `false`       |
| `Sponsor Click`      | the logo link is clicked                                  | default       |

Both carry the properties `sponsor` (the sponsor's slug, falling back to its
name) and `placement` (`pypi-sidebar`). python.org reports `Sponsor Click`
with the same `sponsor` property, so the goals can be shared across sites.
The goals and custom properties must be configured on the Plausible dashboard
for the events to be recorded. Links work whether or not analytics loads.

Plausible ignores events sent from `localhost` and logs them to the browser
console instead, so in development check the console rather than the network
tab.
