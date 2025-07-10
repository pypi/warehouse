# api

This section of the codebase is responsible for the user-facing API views
and associated logic.

Structurally, there are some other modules here that are API-interactions,
but do not live under the `/api/*` route namespace.
They may be refactored to another location at some future point.

We have API endpoints that pre-date the `/api/*` namespace,
see https://docs.pypi.org/api/ for more.

All APIs under the `/api/*` namespace are JSON-only.
