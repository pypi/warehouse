# Release gating

Release gating is a reusable hold on a `Release`. While a gate blocks, the
release is withheld from the Simple index, the JSON API, and the web UI, so no
installer can resolve a version it cannot see.

This is the mechanism only. **Warehouse registers no gates.** With none
registered, uploads take the same path they did before it existed. A feature
that needs to withhold releases registers its own `IGatePolicy`.

## What gating withholds

Gating is discoverability-only. A gated release is excluded from the Simple
index and the JSON API, which is what makes it uninstallable: `pip install foo`
cannot select a version it cannot see. It is also hidden from the web UI: the
project page skips it when choosing which release to show and in its version
history, and requesting a gated version's page directly is a 404. The exclusion
lives in `warehouse/packaging/utils.py`, `warehouse/legacy/api/json.py`, and
`warehouse/packaging/views.py` (with the `Project.all_versions` and
`Project.latest_version` properties in `warehouse/packaging/models.py`), all of
which filter on `Release.gated`.

The files themselves are still synced to the CDN-backed cache bucket on upload,
exactly as for an ungated release, so the artifact stays fetchable by its URL.
File URLs are served directly by the CDN from the bucket and are not checked
against the database per request; the URL carries the file's content hash, so it
is effectively unguessable without the metadata the index withholds. This is
deliberate: a gate hides a release from resolution without destroying the bytes,
so an authorized consumer that already holds the URL (for example a security
scanner granted access) can still pull the artifact to inspect it.

Because gating does not touch caching, nothing in the cache-sync path special-
cases `Release.gated`: `sync_file_to_cache`, `reconcile_file_storages`, and the
`check_file_cache_tasks_outstanding` gauge all treat a gated file like any
other.

## Vocabulary

A `ReleaseGate` row is one hold, identified by `(release_id, kind)`.

`kind` is the name of the `IGatePolicy` that owns the hold. It is a plain
string, not a database enum, which is what makes the set of gates open: adding
one is a code change in one package, with no migration against `release_gates`.
It is validated at registration, which happens at application startup, rather
than at insert time, so a malformed policy fails the deployment instead of an upload.

`GateStatus` is the state of the hold:

| Status | Blocks? | Meaning |
|---|---|---|
| `pending` | yes | Not yet decided |
| `failed` | yes | Decided unfavorably; needs an administrator |
| `passed` | no | Decided favorably by the policy |
| `bypassed` | no | An administrator overrode the policy |
| `expired` | no | The policy never decided and the gate failed open |

Only `pending` and `failed` block. Everything else lets the release through, so
a newly added status defaults to non-blocking and cannot silently strand
releases that were already published.

Gates are never deleted when they resolve, so a release keeps an audit record
of what held it and why it was released. Gate rows therefore outlive the policy
that created them: a `kind` is effectively permanent, and renaming one orphans
its history.

`details` is a JSONB column the mechanism never reads. It is there so a policy
can attach whatever evidence drove its decision without the generic schema
having to know the shape.

### `Release.gated`

`Release.gated` is denormalized from the gate rows: a single indexed boolean
the read paths filter on, so they do not join against the gate rows on every
request.

It is only ever written through `IGateService`, which recomputes it from the
gates whenever one resolves. Writing it directly will desynchronize it from the
gate rows.

## Adding a gate

Implement `IGatePolicy` and register it. That is the whole extension point:
the mechanism does not change and neither does the schema.

```python
@implementer(IGatePolicy)
class MyPolicy:
    kind = "my-gate"
    timeout = datetime.timedelta(hours=2)
    timeout_status = GateStatus.Expired

    def applies(self, release, request):
        return True  # called on every upload; must be cheap and side-effect free
```

```python
def includeme(config):
    config.register_gate_policy(MyPolicy())
```

Register it from a package included *after* `.gating` in
`warehouse/config.py`, since `register_gate_policy` is a directive that package
adds.

A policy decides only *whether a release needs this hold* and *how long it may
stay pending*. It does not resolve its own gates; whatever does the work (a
Celery task, a webhook) calls `IGateService.resolve`.

A policy may resolve its gate the instant it has an answer. The timeout is then
a *ceiling* on the hold rather than a waiting period, and in that case it never
fires.

### Timeouts

`resolve_timed_out_gates` runs every minute and is the backstop that stops a
stalled decision from withholding a release forever. `timeout_status` says what
elapsing means for that policy:

- `Passed`: waiting *is* the mechanism, so the window elapsing is the decision.
- `Expired`: fail open after never getting an answer. Distinct from `Passed`
  so the audit trail separates "decided favorably" from "gave up waiting".
- `Failed`: fail closed, keep withholding.

A policy with `timeout = None` waits indefinitely.

A pending gate whose kind has no registered policy (a retired kind, or a
feature switched off) is expired by the same sweep, because nothing is left
that could decide it. For the same reason `IGateService.resolve` is keyed on
the gate row rather than on the registry: retiring a policy must not make its
outstanding gates unresolvable.

### Reopening

`open_gates` runs on *every* upload, not only on new releases. A file added to
an already-cleared release reopens that release's gates, because the earlier
decision was about the files that existed at the time. The unique constraint on
`(release_id, kind)` means the existing row is reset rather than duplicated.

## Administrative override

`/admin/gating/` lists every gate currently withholding a release and offers a
bypass. A `failed` gate is the only state nothing resolves on its own, so
without a manual bypass a release could be withheld permanently.

A bypass is recorded as `bypassed` rather than `passed`, with the
administrator's username in `resolved_by`, so the audit trail keeps the
distinction between a policy clearing a release and a person overriding it.

## Metrics

| Metric | Meaning |
|---|---|
| `warehouse.gating.gates` | Gauge of gate rows by kind and status |
| `warehouse.gating.timed_out` | A gate was resolved by the timeout sweep |
| `warehouse.upload.gated` | An upload was withheld (one increment per blocking gate kind) |

A rising `warehouse.gating.timed_out` with `status:expired` means releases are
being published without the decision their gate was waiting for.

## Trying it locally

With no policies registered there is nothing to observe, so register one first.
A policy that holds every release until the timeout elapses is enough to watch
the mechanism work end to end.

```shell
make serve
```

Upload a distribution to the local instance. The release is in the database but
absent from the project page, the JSON API, and `/simple/<name>/` while its gate
is pending; its file is still in the cache bucket and fetchable by its URL:

```shell
curl -s http://localhost:80/simple/<name>/ | grep <version>
```

```sql
SELECT r.version, g.kind, g.status, g.resolved, g.note
FROM release_gates g JOIN releases r ON r.id = g.release_id
ORDER BY g.created DESC;
```

The `failed` state is the one that needs the admin bypass at `/admin/gating/`,
so take a gate there to exercise that path.
