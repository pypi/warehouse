# Plan: Adding a New Trusted Publisher to PyPI

This document outlines everything required to add a 5th trusted publisher to the PyPI Warehouse codebase.

---

## Overview

PyPI currently supports 4 trusted publishers (OIDC-based):
1. **GitHub** Actions
2. **GitLab** CI/CD
3. **Google** Cloud
4. **ActiveState**

Each publisher requires a consistent set of components across models, forms, views, templates, migrations, and tests.

---

## Components to Create/Modify

### 1. OIDC Model (Database Layer)

**Create:** `warehouse/oidc/models/<new_publisher>.py`

This file defines the SQLAlchemy models for both the "active" and "pending" publisher types.

**Reference Implementation:** [warehouse/oidc/models/activestate.py](file:///Users/mitchellamihod/src/warehouse/warehouse/oidc/models/activestate.py)

**Required Elements:**
- `<NEW>_OIDC_ISSUER_URL` constant (the OIDC issuer URL for the provider)
- `<New>PublisherMixin` class with:
  - Database columns for publisher-specific fields
  - `__required_verifiable_claims__` dict mapping JWT claims to verification functions
  - `__required_unverifiable_claims__` set
  - `__optional_verifiable_claims__` dict
  - `__unchecked_claims__` set
  - `lookup_by_claims()` classmethod
  - `publisher_name` property
  - `publisher_base_url` property
  - `publisher_url()` method
  - `stored_claims()` method
  - `exists()` method
  - `reify()` method (for pending → active conversion)
  - `__str__` method
- `<New>Publisher(Mixin, OIDCPublisher)` class with unique constraint
- `Pending<New>Publisher(Mixin, PendingOIDCPublisher)` class with unique constraint

---

### 2. Model Exports

**Modify:** [warehouse/oidc/models/__init__.py](file:///Users/mitchellamihod/src/warehouse/warehouse/oidc/models/__init__.py)

- Import the new issuer URL constant
- Import `<New>Publisher` and `Pending<New>Publisher`
- Add all three to `__all__`

---

### 3. OIDC Utils (Publisher Registry)

**Modify:** [warehouse/oidc/utils.py](file:///Users/mitchellamihod/src/warehouse/warehouse/oidc/utils.py)

Update these mappings:
- `OIDC_ISSUER_SERVICE_NAMES` — add `<NEW>_OIDC_ISSUER_URL: "<new>"`
- `OIDC_ISSUER_ADMIN_FLAGS` — add `<NEW>_OIDC_ISSUER_URL: AdminFlagValue.DISALLOW_<NEW>_OIDC`
- `OIDC_PUBLISHER_CLASSES` — add mapping for both Publisher and PendingPublisher

---

### 4. Admin Flag

**Modify:** [warehouse/admin/flags.py](file:///Users/mitchellamihod/src/warehouse/warehouse/admin/flags.py#L11-L23)

Add new enum value:
```python
DISALLOW_<NEW>_OIDC = "disallow-<new>-oidc"
```

---

### 5. OIDC Service Registration

**Modify:** [warehouse/oidc/__init__.py](file:///Users/mitchellamihod/src/warehouse/warehouse/oidc/__init__.py)

Add a new `register_service_factory` call for the new publisher:
```python
config.register_service_factory(
    OIDCPublisherServiceFactory(
        publisher="<new>",
        issuer_url=<NEW>_OIDC_ISSUER_URL,
        service_class=oidc_publisher_service_class,
    ),
    IOIDCPublisherService,
    name="<new>",
)
```

---

### 6. Forms

**Create:** `warehouse/oidc/forms/<new_publisher>.py`

**Reference Implementation:** [warehouse/oidc/forms/activestate.py](file:///Users/mitchellamihod/src/warehouse/warehouse/oidc/forms/activestate.py)

**Required Elements:**
- `<New>PublisherBase(wtforms.Form)` with:
  - `__params__` list of form field names
  - WTForms field definitions with validators
  - Custom validation methods as needed
- `<New>PublisherForm(<New>PublisherBase)` for existing projects
- `Pending<New>PublisherForm(PendingPublisherMixin, <New>PublisherBase)` for pending publishers

**Modify:** [warehouse/oidc/forms/__init__.py](file:///Users/mitchellamihod/src/warehouse/warehouse/oidc/forms/__init__.py)

- Import and export both form classes

---

### 7. Management Views

**Modify:** [warehouse/manage/views/oidc_publishers.py](file:///Users/mitchellamihod/src/warehouse/warehouse/manage/views/oidc_publishers.py)

- Import the new form and model classes
- Add form instance to `ManageOIDCPublisherViews.__init__`
- Add to `default_response` dict (both form and disabled flag)
- Add to `provider_mapping` in `manage_project_oidc_publishers_prefill`
- Create new view method `add_<new>_oidc_publisher` decorated with `@view_config`

**Reference:** See existing `add_activestate_oidc_publisher` method around line 627.

---

### 8. Templates

**Modify:** [warehouse/templates/manage/project/publishing.html](file:///Users/mitchellamihod/src/warehouse/warehouse/templates/manage/project/publishing.html)

- Add a new `<new>_form()` macro (around line 275-355 for ActiveState reference)
- Add the new publisher to the `publishers` list in the tabs section (around line 391-396)

**Potentially Modify:**
- [warehouse/templates/manage/account/publishing.html](file:///Users/mitchellamihod/src/warehouse/warehouse/templates/manage/account/publishing.html) — for pending publishers
- [warehouse/templates/manage/organization/publishing.html](file:///Users/mitchellamihod/src/warehouse/warehouse/templates/manage/organization/publishing.html) — for organization-level publishing

---

### 9. Database Migration

**Create:** New Alembic migration in `warehouse/migrations/versions/`

**Reference Implementation:** [warehouse/migrations/versions/9a0ed2044b53_add_activestate_oidc_publisher.py](file:///Users/mitchellamihod/src/warehouse/warehouse/migrations/versions/9a0ed2044b53_add_activestate_oidc_publisher.py)

**Required Operations:**
- `op.create_table("<new>_oidc_publishers", ...)` with columns and FK to `oidc_publishers.id`
- `op.create_table("pending_<new>_oidc_publishers", ...)` with FK to `pending_oidc_publishers.id`
- Insert admin flag row: `INSERT INTO admin_flags(id, description, enabled, notify) VALUES ('disallow-<new>-oidc', ...)`
- Corresponding `downgrade()` to drop tables and delete flag

---

### 10. Tests

**Create test files:**

| Test File | Reference |
|-----------|-----------|
| `tests/unit/oidc/models/test_<new>.py` | [test_activestate.py](file:///Users/mitchellamihod/src/warehouse/tests/unit/oidc/models/test_activestate.py) |
| `tests/unit/oidc/forms/test_<new>.py` | [test_activestate.py](file:///Users/mitchellamihod/src/warehouse/tests/unit/oidc/forms/test_activestate.py) |

**Modify existing tests:**
- `tests/unit/oidc/test_utils.py` — add new publisher to mapping tests
- `tests/unit/manage/views/test_oidc_publishers.py` — test the new view method
- `tests/unit/email/test_init.py` — if email templates reference publishers

---

## Summary Checklist

| # | Component | Action | Location |
|---|-----------|--------|----------|
| 1 | Model | Create | `warehouse/oidc/models/<new>.py` |
| 2 | Model exports | Modify | `warehouse/oidc/models/__init__.py` |
| 3 | Utils/Registry | Modify | `warehouse/oidc/utils.py` |
| 4 | Admin Flag | Modify | `warehouse/admin/flags.py` |
| 5 | Service registration | Modify | `warehouse/oidc/__init__.py` |
| 6 | Forms | Create | `warehouse/oidc/forms/<new>.py` |
| 7 | Form exports | Modify | `warehouse/oidc/forms/__init__.py` |
| 8 | Views | Modify | `warehouse/manage/views/oidc_publishers.py` |
| 9 | Templates | Modify | `warehouse/templates/manage/project/publishing.html` |
| 10 | Migration | Create | `warehouse/migrations/versions/...` |
| 11 | Model tests | Create | `tests/unit/oidc/models/test_<new>.py` |
| 12 | Form tests | Create | `tests/unit/oidc/forms/test_<new>.py` |
| 13 | View tests | Modify | `tests/unit/manage/views/test_oidc_publishers.py` |

---

## Key Design Decisions

1. **Issuer URL**: You must determine the OIDC issuer URL for the new provider (e.g., `https://token.example.com`)

2. **JWT Claims**: Identify which claims the provider includes in their OIDC tokens and how to verify them

3. **Uniqueness Constraints**: Determine what combination of fields uniquely identifies a publisher configuration

4. **Optional vs Required Fields**: Decide which fields are mandatory for configuration

5. **Attestation Support**: If the provider supports attestations, implement `attestation_identity` property using `pypi_attestations`

6. **URL Verification**: Implement `verify_url()` if the provider has a predictable URL pattern for projects
