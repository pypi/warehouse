# Logging

Warehouse uses [structlog](https://www.structlog.org/) for all application
logging. Every log line, whether it comes from warehouse code, gunicorn,
celery, or a third-party library, flows through a single formatter: readable
aligned columns in development, one JSON object per line in production
(where logs ship to Grafana).

## How to log

Two patterns. Pick the one that matches where your code runs.

### In request-handling code

Views, tweens, and services that receive a `request` use `request.log`. Its
events carry the id of the current request automatically:

```python
def my_view(request):
    request.log.info("project_created", project_name=project.name)
```

### Everywhere else

Tasks, services without a request, CLI commands, and module-level code use a
module-level structlog logger:

```python
import structlog

logger = structlog.get_logger(__name__)


def my_task():
    logger.info("cache_purged", key=key)
```

During request handling and celery task execution this logger carries the
same ambient context described below, so you don't need `request.log` for
that.

Don't use `logging.getLogger()`. It still renders correctly, since
everything funnels through the same formatter, but you lose keyword
arguments and context binding. The exception is a library that requires a
stdlib logger instance.

## Writing effective log events

### Keep the event name static

The first argument is the event: a short, constant description of what
happened. Never interpolate variables into it. Put them in keyword arguments
instead, so Grafana can group, count, and alert on the event, and query the
fields.

```python
# Yes: aggregatable event, queryable fields
logger.warning("Rate limit exceeded", user_id=user.id, limit=limit)

# No: f-strings and %-formatting hide the data inside the string
logger.warning(f"Rate limit exceeded for {user.id} at {limit}")
logger.warning("Rate limit exceeded for %s at %s", user.id, limit)
```

### Log identifiers, not objects

Passing an ORM object serializes its `repr()` and may trigger lazy loads.
Pass the fields you need:

```python
# Yes
logger.info("release_created", project_name=project.name, version=release.version)

# No
logger.info("release_created", project=project, release=release)
```

### Bind shared context once

When several log calls in one unit of work share the same fields, bind them
into the context. Every later log line carries them, including lines from
code you call into:

```python
import structlog

# For the rest of the current request/task:
structlog.contextvars.bind_contextvars(project_name=project.name)

# Scoped to a block:
with structlog.contextvars.bound_contextvars(batch_id=batch_id):
    process(batch)

# On a logger instance you pass around:
log = logger.bind(project_name=project.name)
log.info("validation_started")
log.info("validation_finished")
```

### Exceptions

Inside an `except` block, `logger.exception(...)` logs at ERROR and attaches
the traceback. If you're handling the error and only want a note of it, log
at WARNING with the error as a field:

```python
try:
    cacher.purge_key(key)
except requests.RequestException as exc:
    logger.warning("Error purging cache key", key=key, error=str(exc))
```

### Levels

`debug` for development noise, `info` for notable state changes, `warning`
for unexpected but handled situations, `error` for failures that need
attention.

## What context arrives automatically

- `request.id`: a per-request UUID, bound for every web request and for the
  fabricated request inside celery tasks.
- `task_id` and `task_name`: bound around every celery task run.
- Anything you've added with `bind_contextvars` in the current request/task.

These appear on all log lines emitted while the context is active, from
either pattern.

## How it works

`warehouse/logging.py` configures stdlib `logging` and structlog around a
single [`ProcessorFormatter`](https://www.structlog.org/en/stable/standard-library.html):

- structlog loggers build an event dict and hand it to the formatter intact.
- Foreign records (gunicorn, celery, libraries) pass through a
  `foreign_pre_chain` that normalizes them into the same shape, including
  fields passed via `extra={...}`.
- The final renderer comes from the `warehouse.env` setting:
  `ConsoleRenderer` (columns, colors) in development, `JSONRenderer` in
  production.

Gunicorn access logs are emitted as structured `http_request` events by
`warehouse.logging.GunicornLogger`, wired up via `logger_class` in the
gunicorn configs, so `method`, `path`, `status`, and `duration_ms` are
queryable fields instead of pieces of an Apache-style string. Each access
event also carries `request.id` (stashed into the WSGI environ by the
request tween), so an access line can be joined to the app logs emitted
during the same request. Celery runs with `worker_hijack_root_logger=False`
so worker logs use the same pipeline.
