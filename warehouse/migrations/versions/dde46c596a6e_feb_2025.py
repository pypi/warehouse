# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
February 2025 snapshot.

This migration is a not a real one, but a snapshot of the DB as of February 2025.
Previous migrations have been deleted but are accessible using git magic in this directory,

Revision ID: dde46c596a6e
Revises: None
Create Date: 2025-02-14 09:19:24.793191
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy import FetchedValue
from sqlalchemy.dialects import postgresql

from warehouse.utils.db.types import TZDateTime

revision = "dde46c596a6e"
down_revision = None


def upgrade():
    # Add the missing extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")

    # Add all enum needed
    sa.Enum(
        "bdist_dmg",
        "bdist_dumb",
        "bdist_egg",
        "bdist_msi",
        "bdist_rpm",
        "bdist_wheel",
        "bdist_wininst",
        "sdist",
        name="packagetype",
    ).create(op.get_bind())
    sa.Enum(
        "Platform",
        "Supported-Platform",
        "Summary",
        "Description",
        "Description-Content-Type",
        "Keywords",
        "Home-Page",
        "Download-Url",
        "Author",
        "Author-Email",
        "Maintainer",
        "Maintainer-Email",
        "License",
        "License-Expression",
        "License-File",
        "Classifier",
        "Requires-Dist",
        "Requires-Python",
        "Requires-External",
        "Project-Url",
        "Provides-Extra",
        "Provides-Dist",
        "Obsoletes-Dist",
        "Requires",
        "Provides",
        "Obsoletes",
        name="release_dynamic_fields",
    ).create(op.get_bind())
    sa.Enum(
        "quarantine-enter", "quarantine-exit", "archived", name="lifecyclestatus"
    ).create(op.get_bind())
    sa.Enum("pending", "expired", name="roleinvitationstatus").create(op.get_bind())
    sa.Enum(
        "month", "year", "week", "day", name="stripesubscriptionpriceinterval"
    ).create(op.get_bind())
    sa.Enum(
        "active",
        "past_due",
        "unpaid",
        "canceled",
        "incomplete",
        "incomplete_expired",
        "trialing",
        name="stripesubscriptionstatus",
    ).create(op.get_bind())
    sa.Enum("Owner", "Maintainer", name="teamprojectroletype").create(op.get_bind())
    sa.Enum("Member", name="teamroletype").create(op.get_bind())
    sa.Enum("pending", "expired", name="organizationinvitationstatus").create(
        op.get_bind()
    )
    sa.Enum("Community", "Company", name="organizationtype").create(op.get_bind())
    sa.Enum(
        "Owner", "Billing Manager", "Manager", "Member", name="organizationroletype"
    ).create(op.get_bind())
    sa.Enum("Delivery", "Bounce", "Complaint", name="eventtypes").create(op.get_bind())
    sa.Enum(
        "Accepted",
        "Delivered",
        "Bounced",
        "Soft Bounced",
        "Complained",
        name="emailstatuses",
    ).create(op.get_bind())
    sa.Enum(
        "spam complaint", "hard bounce", "soft bounce", name="unverifyreasons"
    ).create(op.get_bind())
    sa.Enum(
        "password compromised",
        "account frozen",
        "admin initiated",
        name="disablereason",
    ).create(op.get_bind())
    sa.Enum("authentication-attempts", name="banreason").create(op.get_bind())

    # Add tables
    op.create_table(
        "admin_flags",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "notify", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Admin flag have been added in different migrations, let's add them all at once here with their latest value
    op.execute(
        """
        INSERT INTO admin_flags (id, description, enabled, notify) VALUES
        ('disallow-new-user-registration', 'Disallow ALL new User registrations', false, false),
        ('disallow-new-project-registration', 'Disallow ALL new Project registrations', false, false),
        ('read-only', 'Read-only mode: Any write operations will have no effect', false, true),
        ('disallow-deletion', 'Disallow ALL project and release deletions', false, false),
        ('disallow-new-upload', 'Disallow ALL new uploads', false, false),
        ('disallow-oidc', 'Disallow ALL OpenID Connect behavior, including authentication', false, false),
        ('disable-organizations', 'Disallow ALL functionality for Organizations', true, false),
        ('disallow-github-oidc', 'Disallow the GitHub OIDC provider', false, false),
        ('disallow-google-oidc', 'Disallow the Google OIDC provider', false, false),
        ('disallow-activestate-oidc', 'Disallow the ActiveState OIDC provider', true, false),
        ('disallow-gitlab-oidc', 'Disallow the GitLab OIDC provider', true, false),
        ('disable-pep740', 'Disable PEP 740 support.', false, false)
    """
    )

    op.create_table(
        "banners",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("link_url", sa.String(), nullable=False),
        sa.Column("link_label", sa.String(), nullable=False),
        sa.Column("fa_icon", sa.String(), nullable=False),
        sa.Column(
            "dismissable", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename"),
    )
    op.create_table(
        "ip_addresses",
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=False,
            comment="Structured IP Address value",
        ),
        sa.Column(
            "hashed_ip_address",
            sa.String(),
            nullable=True,
            comment="Hash that represents an IP Address",
        ),
        sa.Column(
            "geoip_info",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JSON containing GeoIP data associated with an IP Address",
        ),
        sa.Column(
            "is_banned",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="If True, this IP Address will be marked as banned",
        ),
        sa.Column(
            "ban_reason",
            postgresql.ENUM(
                "authentication-attempts", name="banreason", create_type=False
            ),
            nullable=True,
            comment="Reason for banning, must be in the BanReason enumeration",
        ),
        sa.Column(
            "ban_date",
            sa.DateTime(),
            nullable=True,
            comment="Date that IP Address was last marked as banned",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "(is_banned AND ban_reason IS NOT NULL AND ban_date IS NOT NULL)OR (NOT is_banned AND ban_reason IS NULL AND ban_date IS NULL)"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hashed_ip_address"),
        sa.UniqueConstraint("ip_address"),
        comment="Tracks IP Addresses that have modified PyPI state",
    )
    op.create_index("bans_idx", "ip_addresses", ["is_banned"], unique=False)
    op.create_table(
        "observer_association",
        sa.Column(
            "discriminator",
            sa.String(),
            nullable=False,
            comment="The type of the parent",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "oidc_publishers",
        sa.Column("discriminator", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "organization_name_catalog",
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_name",
            "organization_id",
            name="_organization_name_catalog_normalized_name_organization_uc",
        ),
    )
    op.create_index(
        op.f("ix_organization_name_catalog_normalized_name"),
        "organization_name_catalog",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_name_catalog_organization_id"),
        "organization_name_catalog",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "organization_name_catalog_normalized_name_idx",
        "organization_name_catalog",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        "organization_name_catalog_organization_id_idx",
        "organization_name_catalog",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "organizations",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="When True, the organization is active and all features are available.",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Datetime the organization was created.",
        ),
        sa.Column(
            "date_approved",
            sa.DateTime(),
            nullable=True,
            comment="Datetime the organization was approved by administrators.",
        ),
        sa.Column(
            "name", sa.String(), nullable=False, comment="The account name used in URLS"
        ),
        sa.Column(
            "display_name",
            sa.String(),
            nullable=False,
            comment="Display name used in UI",
        ),
        sa.Column(
            "orgtype",
            postgresql.ENUM(
                "Community", "Company", name="organizationtype", create_type=False
            ),
            nullable=False,
            comment="What type of organization such as Community or Company",
        ),
        sa.Column(
            "link_url",
            sa.String(),
            nullable=False,
            comment="External URL associated with the organization",
        ),
        sa.Column(
            "description",
            sa.String(),
            nullable=False,
            comment="Description of the business or project the organization represents",
        ),
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=True,
            comment="Status of administrator approval of the request",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "link_url ~* '^https?://.*'::text", name="organizations_valid_link_url"
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="organizations_valid_name",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organizations_created"), "organizations", ["created"], unique=False
    )
    op.create_table(
        "projects",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "normalized_name",
            sa.String(),
            server_default=FetchedValue(),
            nullable=False,
        ),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
        sa.Column("has_docs", sa.Boolean(), nullable=True),
        sa.Column("upload_limit", sa.Integer(), nullable=True),
        sa.Column("total_size_limit", sa.BigInteger(), nullable=True),
        sa.Column(
            "last_serial", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "total_size", sa.BigInteger(), server_default=sa.text("0"), nullable=True
        ),
        sa.Column(
            "lifecycle_status",
            postgresql.ENUM(
                "quarantine-enter",
                "quarantine-exit",
                "archived",
                name="lifecyclestatus",
                create_type=False,
            ),
            nullable=True,
            comment="Lifecycle status can change project visibility and access",
        ),
        sa.Column(
            "lifecycle_status_changed",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
            comment="When the lifecycle status was last changed",
        ),
        sa.Column(
            "lifecycle_status_note",
            sa.String(),
            nullable=True,
            comment="Note about the lifecycle status",
        ),
        sa.Column(
            "sitemap_bucket", sa.String(), server_default=FetchedValue(), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="projects_valid_name",
        ),
        sa.CheckConstraint(
            "upload_limit <= 1073741824", name="projects_upload_limit_max_value"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.execute(
        """
          CREATE OR REPLACE FUNCTION maintain_project_last_serial()
          RETURNS trigger
          LANGUAGE plpgsql
          AS $$
          DECLARE
              targeted_name text;
          BEGIN
              IF TG_OP = 'INSERT' THEN
                  targeted_name := NEW.name;
              ELSEIF TG_OP = 'UPDATE' THEN
                  targeted_name := NEW.name;
              ELSIF TG_OP = 'DELETE' THEN
                  targeted_name := OLD.name;
              END IF;

              UPDATE projects
              SET last_serial = j.last_serial
              FROM (
                  SELECT max(id) as last_serial
                  FROM journals
                  WHERE journals.name = targeted_name
              ) as j
              WHERE projects.name = targeted_name;

              RETURN NULL;
          END;
          $$
      """
    )

    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION ultranormalize_name(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE STRICT
        AS $$
            SELECT lower(
                regexp_replace(
                    regexp_replace(
                        regexp_replace($1, '(\.|_|-)', '', 'ig'),
                        '(l|L|i|I)', '1', 'ig'
                    ),
                    '(o|O)', '0', 'ig'
                )
            )
        $$
    """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sitemap_bucket(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE STRICT
        AS $$
            SELECT substring(
                encode(digest($1, 'sha512'), 'hex')
                from 1
                for 2
            )
        $$
    """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION maintain_project_sitemap_bucket()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.sitemap_bucket := sitemap_bucket(NEW.name);
            RETURN NEW;
        END;
        $$
    """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION normalize_pep426_name(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE STRICT
        AS $$
            SELECT lower(regexp_replace($1, '(\.|_|-)+', '-', 'ig'))
        $$
    """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION maintain_projects_normalized_name()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.normalized_name := normalize_pep426_name(NEW.name);
            RETURN NEW;
        END;
        $$
    """
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION projects_total_size_releases()
        RETURNS TRIGGER AS $$
        DECLARE
            _project_id uuid;
        BEGIN
            _project_id := OLD.project_id;
            UPDATE projects
            SET total_size=t.project_total_size
            FROM (
            SELECT COALESCE(SUM(release_files.size), 0) AS project_total_size
            FROM release_files WHERE release_id IN
                (SELECT id FROM releases WHERE releases.project_id = _project_id)
            ) AS t
            WHERE id=_project_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION projects_total_size_release_files()
        RETURNS TRIGGER AS $$
        DECLARE
            _release_id uuid;
            _project_id uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                _release_id := NEW.release_id;
            ELSEIF TG_OP = 'UPDATE' THEN
                _release_id := NEW.release_id;
            ELSIF TG_OP = 'DELETE' THEN
                _release_id := OLD.release_id;
            END IF;
            _project_id := (SELECT project_id
                            FROM releases
                            WHERE releases.id=_release_id);
            UPDATE projects
            SET total_size=t.project_total_size
            FROM (
            SELECT COALESCE(SUM(release_files.size), 0) AS project_total_size
            FROM release_files WHERE release_id IN
                (SELECT id FROM releases WHERE releases.project_id = _project_id)
            ) AS t
            WHERE id=_project_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER projects_update_sitemap_bucket
        BEFORE INSERT OR UPDATE OF name ON projects
        FOR EACH ROW
        EXECUTE FUNCTION maintain_project_sitemap_bucket()
    """
    )
    op.execute(
        """
        CREATE TRIGGER projects_update_normalized_name
        BEFORE INSERT OR UPDATE OF name ON projects
        FOR EACH ROW
        EXECUTE FUNCTION maintain_projects_normalized_name()
    """
    )

    op.create_index(op.f("ix_projects_created"), "projects", ["created"], unique=False)
    op.create_index(
        op.f("ix_projects_sitemap_bucket"), "projects", ["sitemap_bucket"], unique=False
    )
    op.create_index(
        "project_name_ultranormalized",
        "projects",
        [sa.text("ultranormalize_name(name)")],
        unique=False,
    )
    op.create_index(
        "projects_lifecycle_status_idx", "projects", ["lifecycle_status"], unique=False
    )
    op.create_table(
        "release_descriptions",
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("raw", sa.String(), nullable=False),
        sa.Column("html", sa.String(), nullable=False),
        sa.Column("rendered_by", sa.String(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "row_counts",
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column(
            "count", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("table_name"),
    )
    op.bulk_insert(
        sa.table(
            "row_counts",
            sa.Column("table_name", sa.Text),
            sa.Column("count", sa.Integer),
        ),
        [
            {"table_name": "releases", "count": 0},
            {"table_name": "release_files", "count": 0},
            {"table_name": "projects", "count": 0},
            {"table_name": "users", "count": 0},
        ],
    )

    op.create_table(
        "ses_emails",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "Accepted",
                "Delivered",
                "Bounced",
                "Soft Bounced",
                "Complained",
                name="emailstatuses",
                create_type=False,
            ),
            server_default="Accepted",
            nullable=False,
        ),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("from", sa.String(), nullable=False),
        sa.Column("to", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column(
            "missing", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ses_emails_message_id"), "ses_emails", ["message_id"], unique=True
    )
    op.create_index(op.f("ix_ses_emails_to"), "ses_emails", ["to"], unique=False)
    op.create_table(
        "sponsors",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("service", sa.String(), nullable=True),
        sa.Column("activity_markdown", sa.String(), nullable=True),
        sa.Column("link_url", sa.String(), nullable=False),
        sa.Column("color_logo_url", sa.String(), nullable=False),
        sa.Column("white_logo_url", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("footer", sa.Boolean(), nullable=False),
        sa.Column("psf_sponsor", sa.Boolean(), nullable=False),
        sa.Column("infra_sponsor", sa.Boolean(), nullable=False),
        sa.Column("one_time", sa.Boolean(), nullable=False),
        sa.Column("sidebar", sa.Boolean(), nullable=False),
        sa.Column("origin", sa.String(), nullable=True),
        sa.Column("level_name", sa.String(), nullable=True),
        sa.Column("level_order", sa.Integer(), nullable=True),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "stripe_customers",
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("billing_email", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id"),
    )
    op.create_table(
        "stripe_subscription_products",
        sa.Column("product_id", sa.String(), nullable=True),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("tax_code", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trove_classifiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("classifier", sa.String(), nullable=True),
        sa.Column("ordering", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("classifier"),
        sa.CheckConstraint("classifier not ilike 'private ::%'", name="ck_disallow_private_top_level_classifier")
    )
    op.create_table(
        "vulnerabilities",
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("link", sa.String(), nullable=True),
        sa.Column("aliases", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("fixed_in", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("withdrawn", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("source", "id"),
    )
    op.create_table(
        "activestate_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("activestate_project_name", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization",
            "activestate_project_name",
            "actor_id",
            name="_activestate_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "alternate_repositories",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "url ~* '^https?://.+'::text", name="alternate_repository_valid_url"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
        sa.UniqueConstraint("project_id", "url"),
    )
    op.create_table(
        "github_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_name", sa.String(), nullable=False),
        sa.Column("repository_owner", sa.String(), nullable=False),
        sa.Column("repository_owner_id", sa.String(), nullable=False),
        sa.Column("workflow_filename", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            "environment",
            name="_github_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "gitlab_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("workflow_filepath", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "namespace",
            "project",
            "workflow_filepath",
            "environment",
            name="_gitlab_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "google_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("sub", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "sub", name="_google_oidc_publisher_uc"),
    )
    op.create_table(
        "observers",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("_association_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["_association_id"],
            ["observer_association.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "oidc_publisher_project_association",
        sa.Column("oidc_publisher_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["oidc_publisher_id"],
            ["oidc_publishers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("oidc_publisher_id", "project_id", "id"),
    )
    op.create_table(
        "organization_events",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organization_events_source_id",
        "organization_events",
        ["source_id"],
        unique=False,
    )
    op.create_table(
        "organization_projects",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "project_id",
            name="_organization_projects_organization_project_uc",
        ),
    )
    op.create_index(
        "organization_projects_organization_id_idx",
        "organization_projects",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "organization_projects_project_id_idx",
        "organization_projects",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "organization_stripe_customers",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("stripe_customer_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stripe_customer_id"],
            ["stripe_customers.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "stripe_customer_id",
            name="_organization_stripe_customers_organization_customer_uc",
        ),
    )
    op.create_index(
        "organization_stripe_customers_organization_id_idx",
        "organization_stripe_customers",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "organization_stripe_customers_stripe_customer_id_idx",
        "organization_stripe_customers",
        ["stripe_customer_id"],
        unique=False,
    )
    op.create_table(
        "organization_terms_of_service_agreements",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("agreed", TZDateTime(), nullable=True),
        sa.Column("notified", TZDateTime(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "organization_terms_of_service_agreements_organization_id_idx",
        "organization_terms_of_service_agreements",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "project_events",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["projects.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_events_source_id", "project_events", ["source_id"], unique=False
    )
    op.create_table(
        "ses_events",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("email_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "Delivery", "Bounce", "Complaint", name="eventtypes", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["email_id"],
            ["ses_emails.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ses_events_email_id"), "ses_events", ["email_id"], unique=False
    )
    op.create_index(
        op.f("ix_ses_events_event_id"), "ses_events", ["event_id"], unique=True
    )
    op.create_table(
        "stripe_subscription_prices",
        sa.Column("price_id", sa.String(), nullable=True),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("subscription_product_id", sa.UUID(), nullable=False),
        sa.Column("unit_amount", sa.Integer(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "recurring",
            postgresql.ENUM(
                "month",
                "year",
                "week",
                "day",
                name="stripesubscriptionpriceinterval",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("tax_behavior", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["subscription_product_id"],
            ["stripe_subscription_products.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "teams",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "name ~* '^([^\\s/._-]|[^\\s/._-].*[^\\s/._-])$'::text",
            name="teams_valid_name",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        r""" CREATE OR REPLACE FUNCTION normalize_team_name(text)
            RETURNS text AS
            $$
                SELECT lower(regexp_replace($1, '(\s|/|\.|_|-)+', '-', 'ig'))
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
        """
    )
    op.create_index(op.f("ix_teams_created"), "teams", ["created"], unique=False)
    op.create_index(
        "teams_organization_id_idx", "teams", ["organization_id"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("username", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("password", sa.String(length=128), nullable=False),
        sa.Column(
            "password_date",
            TZDateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_frozen", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_support", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_moderator",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_psf_staff",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_observer",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Is this user allowed to add Observations?",
        ),
        sa.Column(
            "prohibit_password_reset",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "hide_avatar", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "date_joined", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
        sa.Column(
            "last_login",
            TZDateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "disabled_for",
            postgresql.ENUM(
                "password compromised",
                "account frozen",
                "admin initiated",
                name="disablereason",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("totp_secret", sa.LargeBinary(length=20), nullable=True),
        sa.Column("last_totp_value", sa.String(), nullable=True),
        sa.Column(
            "sitemap_bucket", sa.String(), server_default=FetchedValue(), nullable=False
        ),
        sa.Column("observer_association_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="users_valid_username",
        ),
        sa.CheckConstraint(
            "length(username) <= 50", name="users_valid_username_length"
        ),
        sa.ForeignKeyConstraint(
            ["observer_association_id"],
            ["observer_association.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION maintain_accounts_user_sitemap_bucket()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.sitemap_bucket := sitemap_bucket(NEW.username);
            RETURN NEW;
        END;
        $$
    """
    )
    op.execute(
        """
        CREATE TRIGGER accounts_user_update_sitemap_bucket
        BEFORE INSERT OR UPDATE OF username ON users
        FOR EACH ROW
        EXECUTE FUNCTION maintain_accounts_user_sitemap_bucket()
    """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_password_date()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.password_date = now();
            RETURN NEW;
        END;
        $$
    """
    )
    op.execute(
        """
        CREATE TRIGGER update_user_password_date
        BEFORE UPDATE OF password ON users
        FOR EACH ROW
        WHEN ((old.password)::text IS DISTINCT FROM (new.password)::text)
        EXECUTE FUNCTION update_password_date()
    """
    )
    op.create_index(
        op.f("ix_users_sitemap_bucket"), "users", ["sitemap_bucket"], unique=False
    )
    op.create_table(
        "journals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column(
            "submitted_date",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_by", postgresql.CITEXT(), nullable=True),
        sa.ForeignKeyConstraint(
            ["submitted_by"], ["users.username"], onupdate="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        CREATE TRIGGER update_project_last_serial
        AFTER INSERT OR DELETE OR UPDATE ON journals
        FOR EACH ROW
        EXECUTE FUNCTION maintain_project_last_serial()
    """
    )
    op.create_index(
        "journals_changelog",
        "journals",
        ["submitted_date", "name", "version", "action"],
        unique=False,
    )
    op.create_index("journals_name_idx", "journals", ["name"], unique=False)
    op.create_index(
        "journals_submitted_by_and_reverse_date_idx",
        "journals",
        ["submitted_by", sa.text("submitted_date DESC")],
        unique=False,
    )
    op.create_index(
        "journals_submitted_by_idx", "journals", ["submitted_by"], unique=False
    )
    op.create_index(
        "journals_submitted_date_id_idx",
        "journals",
        ["submitted_date", "id"],
        unique=False,
    )
    op.create_index("journals_version_idx", "journals", ["version"], unique=False)
    op.create_table(
        "macaroons",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("oidc_publisher_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("last_used", sa.DateTime(), nullable=True),
        sa.Column(
            "permissions_caveat",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "caveats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="The list of caveats that were attached to this Macaroon when we generated it. Users can add additional caveats at any time without communicating those additional caveats to us, which would not be reflected in this data, and thus this field must only be used for informational purposes and must not be used during the authorization or authentication process. Older Macaroons may be missing caveats as previously only the legacy permissions caveat were stored.",
        ),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("key", sa.LargeBinary(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "(user_id::text IS NULL) <> (oidc_publisher_id::text IS NULL)",
            name="_user_xor_oidc_publisher_macaroon",
        ),
        sa.ForeignKeyConstraint(
            ["oidc_publisher_id"],
            ["oidc_publishers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "description", "user_id", name="_user_macaroons_description_uc"
        ),
    )
    op.create_index(
        op.f("ix_macaroons_oidc_publisher_id"),
        "macaroons",
        ["oidc_publisher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_macaroons_user_id"), "macaroons", ["user_id"], unique=False
    )
    op.create_table(
        "organization_applications",
        sa.Column(
            "submitted_by_id",
            sa.UUID(),
            nullable=False,
            comment="ID of the User which submitted the request",
        ),
        sa.Column(
            "submitted",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Datetime the request was submitted",
        ),
        sa.Column(
            "organization_id",
            sa.UUID(),
            nullable=True,
            comment="If the request was approved, ID of resulting Organization",
        ),
        sa.Column(
            "name", sa.String(), nullable=False, comment="The account name used in URLS"
        ),
        sa.Column(
            "display_name",
            sa.String(),
            nullable=False,
            comment="Display name used in UI",
        ),
        sa.Column(
            "orgtype",
            postgresql.ENUM(
                "Community", "Company", name="organizationtype", create_type=False
            ),
            nullable=False,
            comment="What type of organization such as Community or Company",
        ),
        sa.Column(
            "link_url",
            sa.String(),
            nullable=False,
            comment="External URL associated with the organization",
        ),
        sa.Column(
            "description",
            sa.String(),
            nullable=False,
            comment="Description of the business or project the organization represents",
        ),
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=True,
            comment="Status of administrator approval of the request",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "link_url ~* '^https?://.*'::text",
            name="organization_applications_valid_link_url",
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="organization_applications_valid_name",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_id"],
            ["users.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organization_applications_submitted"),
        "organization_applications",
        ["submitted"],
        unique=False,
    )
    op.create_table(
        "organization_invitations",
        sa.Column(
            "invite_status",
            postgresql.ENUM(
                "pending",
                "expired",
                name="organizationinvitationstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "organization_id",
            name="_organization_invitations_user_organization_uc",
        ),
    )
    op.create_index(
        op.f("ix_organization_invitations_organization_id"),
        "organization_invitations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invitations_user_id"),
        "organization_invitations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "organization_invitations_user_id_idx",
        "organization_invitations",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "organization_roles",
        sa.Column(
            "role_name",
            postgresql.ENUM(
                "Owner",
                "Billing Manager",
                "Manager",
                "Member",
                name="organizationroletype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "organization_id",
            name="_organization_roles_user_organization_uc",
        ),
    )
    op.create_index(
        "organization_roles_organization_id_idx",
        "organization_roles",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "organization_roles_user_id_idx",
        "organization_roles",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "pending_oidc_publishers",
        sa.Column("project_name", sa.String(), nullable=False),
        sa.Column("added_by_id", sa.UUID(), nullable=False),
        sa.Column("discriminator", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pending_oidc_publishers_added_by_id"),
        "pending_oidc_publishers",
        ["added_by_id"],
        unique=False,
    )
    op.create_index(
        "pending_project_name_ultranormalized",
        "pending_oidc_publishers",
        [sa.text("ultranormalize_name(project_name)")],
        unique=False,
    )
    op.create_table(
        "prohibited_email_domains",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column(
            "is_mx_record",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Prohibit any domains that have this domain as an MX record?",
        ),
        sa.Column("prohibited_by", sa.UUID(), nullable=True),
        sa.Column("comment", sa.String(), server_default="", nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["prohibited_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index(
        op.f("ix_prohibited_email_domains_prohibited_by"),
        "prohibited_email_domains",
        ["prohibited_by"],
        unique=False,
    )
    op.create_table(
        "prohibited_project_names",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prohibited_by", sa.UUID(), nullable=True),
        sa.Column("comment", sa.String(), server_default="", nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="prohibited_project_valid_name",
        ),
        sa.ForeignKeyConstraint(
            ["prohibited_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.execute(
        """ CREATE OR REPLACE FUNCTION ensure_normalized_prohibited_project_names()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.name = normalize_pep426_name(NEW.name);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """ CREATE TRIGGER normalize_prohibited_project_names
            BEFORE INSERT OR UPDATE ON prohibited_project_names
            FOR EACH ROW EXECUTE PROCEDURE ensure_normalized_prohibited_project_names();
        """
    )

    op.execute(
        "INSERT INTO prohibited_project_names (name) VALUES ('requirements.txt')"
    )
    op.execute(
        "INSERT INTO prohibited_project_names (name) VALUES ('rrequirements.txt')"
    )
    op.create_index(
        op.f("ix_prohibited_project_names_prohibited_by"),
        "prohibited_project_names",
        ["prohibited_by"],
        unique=False,
    )
    op.create_table(
        "prohibited_user_names",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prohibited_by", sa.UUID(), nullable=True),
        sa.Column("comment", sa.String(), server_default="", nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="prohibited_users_valid_username",
        ),
        sa.CheckConstraint(
            "length(name) <= 50", name="prohibited_users_valid_username_length"
        ),
        sa.ForeignKeyConstraint(
            ["prohibited_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_prohibited_user_names_prohibited_by"),
        "prohibited_user_names",
        ["prohibited_by"],
        unique=False,
    )
    op.create_table(
        "project_observations",
        sa.Column(
            "related_id",
            sa.UUID(),
            nullable=True,
            comment="The ID of the related model",
        ),
        sa.Column(
            "related_name",
            sa.String(),
            nullable=False,
            comment="The name of the related model",
        ),
        sa.Column(
            "observer_id",
            sa.UUID(),
            nullable=False,
            comment="ID of the Observer who created the Observation",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="The time the observation was created",
        ),
        sa.Column(
            "kind", sa.String(), nullable=False, comment="The kind of observation"
        ),
        sa.Column(
            "summary",
            sa.String(),
            nullable=False,
            comment="A short summary of the observation",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="The observation payload we received",
        ),
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["observer_id"],
            ["observers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["related_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_observations_related_id"),
        "project_observations",
        ["related_id"],
        unique=False,
    )
    op.create_table(
        "releases",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("canonical_version", sa.String(), nullable=False),
        sa.Column(
            "is_prerelease",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("author_email", sa.String(), nullable=True),
        sa.Column(
            "author_email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("maintainer", sa.String(), nullable=True),
        sa.Column("maintainer_email", sa.String(), nullable=True),
        sa.Column(
            "maintainer_email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("home_page", sa.String(), nullable=True),
        sa.Column(
            "home_page_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("license", sa.String(), nullable=True),
        sa.Column("license_expression", sa.String(), nullable=True),
        sa.Column(
            "license_files",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment="Array of license filenames. Null indicates no License-File(s) were supplied by the uploader.",
        ),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("keywords", sa.String(), nullable=True),
        sa.Column(
            "keywords_array",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment="Array of keywords. Null indicates no keywords were supplied by the uploader.",
        ),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("download_url", sa.String(), nullable=True),
        sa.Column(
            "download_url_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("_pypi_ordering", sa.Integer(), nullable=True),
        sa.Column("requires_python", sa.Text(), nullable=True),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "published", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("description_id", sa.UUID(), nullable=False),
        sa.Column(
            "yanked", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("yanked_reason", sa.String(), server_default="", nullable=False),
        sa.Column(
            "dynamic",
            postgresql.ARRAY(
                postgresql.ENUM(
                    "Platform",
                    "Supported-Platform",
                    "Summary",
                    "Description",
                    "Description-Content-Type",
                    "Keywords",
                    "Home-Page",
                    "Download-Url",
                    "Author",
                    "Author-Email",
                    "Maintainer",
                    "Maintainer-Email",
                    "License",
                    "License-Expression",
                    "License-File",
                    "Classifier",
                    "Requires-Dist",
                    "Requires-Python",
                    "Requires-External",
                    "Project-Url",
                    "Provides-Extra",
                    "Provides-Dist",
                    "Obsoletes-Dist",
                    "Requires",
                    "Provides",
                    "Obsoletes",
                    name="release_dynamic_fields",
                    create_type=False,
                )
            ),
            nullable=True,
            comment="Array of metadata fields marked as Dynamic (PEP 643/Metadata 2.2)",
        ),
        sa.Column(
            "provides_extra",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="Array of extra names (PEP 566/685|Metadata 2.1/2.3)",
        ),
        sa.Column("uploader_id", sa.UUID(), nullable=True),
        sa.Column("uploaded_via", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["description_id"],
            ["release_descriptions.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploader_id"], ["users.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version"),
    )
    op.execute(
        """
        CREATE TRIGGER update_project_total_size_releases
        AFTER DELETE ON releases
        FOR EACH ROW
        EXECUTE FUNCTION projects_total_size_releases()
    """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pep440_is_prerelease(text)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE STRICT
        AS $$
            SELECT lower($1) ~* '(a|b|rc|dev|alpha|beta|c|pre|preview)'
        $$
    """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION maintain_releases_is_prerelease()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
            BEGIN
                NEW.is_prerelease := pep440_is_prerelease(NEW.version);
                RETURN NEW;
            END;
        $$
    """
    )
    op.execute(
        """
        CREATE TRIGGER releases_update_is_prerelease
        BEFORE INSERT OR UPDATE OF version ON releases
        FOR EACH ROW
        EXECUTE FUNCTION maintain_releases_is_prerelease()
    """
    )
    op.create_index(
        op.f("ix_releases_description_id"), "releases", ["description_id"], unique=False
    )
    op.create_index(
        op.f("ix_releases_uploader_id"), "releases", ["uploader_id"], unique=False
    )
    op.create_index(
        "release_canonical_version_idx", "releases", ["canonical_version"], unique=False
    )
    op.create_index(
        "release_created_idx", "releases", [sa.text("created DESC")], unique=False
    )
    op.create_index(
        "release_project_created_idx",
        "releases",
        ["project_id", sa.text("created DESC")],
        unique=False,
    )
    op.create_index("release_version_idx", "releases", ["version"], unique=False)
    op.create_table(
        "role_invitations",
        sa.Column(
            "invite_status",
            postgresql.ENUM(
                "pending", "expired", name="roleinvitationstatus", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "project_id", name="_role_invitations_user_project_uc"
        ),
    )
    op.create_index(
        op.f("ix_role_invitations_project_id"),
        "role_invitations",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_role_invitations_user_id"),
        "role_invitations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "role_invitations_user_id_idx", "role_invitations", ["user_id"], unique=False
    )
    op.create_table(
        "roles",
        sa.Column("role_name", sa.String(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "project_id", name="_roles_user_project_uc"),
    )
    op.create_index("roles_project_id_idx", "roles", ["project_id"], unique=False)
    op.create_index("roles_user_id_idx", "roles", ["user_id"], unique=False)
    op.create_table(
        "stripe_subscriptions",
        sa.Column("stripe_customer_id", sa.UUID(), nullable=False),
        sa.Column("subscription_id", sa.String(), nullable=False),
        sa.Column("subscription_price_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "past_due",
                "unpaid",
                "canceled",
                "incomplete",
                "incomplete_expired",
                "trialing",
                name="stripesubscriptionstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["stripe_customer_id"],
            ["stripe_customers.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_price_id"],
            ["stripe_subscription_prices.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stripe_customer_id",
            "subscription_id",
            name="_stripe_subscription_customer_subscription_uc",
        ),
    )
    op.create_index(
        "stripe_subscriptions_stripe_customer_id_idx",
        "stripe_subscriptions",
        ["stripe_customer_id"],
        unique=False,
    )
    op.create_index(
        "stripe_subscriptions_subscription_id_idx",
        "stripe_subscriptions",
        ["subscription_id"],
        unique=False,
    )
    op.create_table(
        "team_events",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["teams.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_team_events_source_id", "team_events", ["source_id"], unique=False
    )
    op.create_table(
        "team_project_roles",
        sa.Column(
            "role_name",
            postgresql.ENUM(
                "Owner", "Maintainer", name="teamprojectroletype", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "team_id", name="_team_project_roles_project_team_uc"
        ),
    )
    op.create_index(
        "team_project_roles_project_id_idx",
        "team_project_roles",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "team_project_roles_team_id_idx",
        "team_project_roles",
        ["team_id"],
        unique=False,
    )
    op.create_table(
        "team_roles",
        sa.Column(
            "role_name",
            postgresql.ENUM("Member", name="teamroletype", create_type=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "team_id", name="_team_roles_user_team_uc"),
    )
    op.create_index("team_roles_team_id_idx", "team_roles", ["team_id"], unique=False)
    op.create_index("team_roles_user_id_idx", "team_roles", ["user_id"], unique=False)
    op.create_table(
        "user_emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("primary", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column(
            "public", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "unverify_reason",
            postgresql.ENUM(
                "spam complaint",
                "hard bounce",
                "soft bounce",
                name="unverifyreasons",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "transient_bounces",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="user_emails_email_key"),
    )
    op.create_index("user_emails_user_id", "user_emails", ["user_id"], unique=False)
    op.create_table(
        "user_events",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["users.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_events_source_id", "user_events", ["source_id"], unique=False
    )
    op.create_table(
        "user_observations",
        sa.Column(
            "related_id",
            sa.UUID(),
            nullable=True,
            comment="The ID of the related model",
        ),
        sa.Column(
            "related_name",
            sa.String(),
            nullable=False,
            comment="The name of the related model",
        ),
        sa.Column(
            "observer_id",
            sa.UUID(),
            nullable=False,
            comment="ID of the Observer who created the Observation",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="The time the observation was created",
        ),
        sa.Column(
            "kind", sa.String(), nullable=False, comment="The kind of observation"
        ),
        sa.Column(
            "summary",
            sa.String(),
            nullable=False,
            comment="A short summary of the observation",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="The observation payload we received",
        ),
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["observer_id"],
            ["observers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["related_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_observations_related_id"),
        "user_observations",
        ["related_id"],
        unique=False,
    )
    op.create_table(
        "user_recovery_codes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column(
            "generated", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("burned", sa.DateTime(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_recovery_codes_user_id"),
        "user_recovery_codes",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "user_security_keys",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("credential_id", sa.String(), nullable=False),
        sa.Column("public_key", sa.String(), nullable=True),
        sa.Column("sign_count", sa.Integer(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
        sa.UniqueConstraint("label", "user_id", name="_user_security_keys_label_uc"),
        sa.UniqueConstraint("public_key"),
    )
    op.create_index(
        op.f("ix_user_security_keys_user_id"),
        "user_security_keys",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "organization_stripe_subscriptions",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["stripe_subscriptions.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "subscription_id",
            name="_organization_stripe_subscriptions_organization_subscription_uc",
        ),
    )
    op.create_index(
        "organization_stripe_subscriptions_organization_id_idx",
        "organization_stripe_subscriptions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "organization_stripe_subscriptions_subscription_id_idx",
        "organization_stripe_subscriptions",
        ["subscription_id"],
        unique=False,
    )
    op.create_table(
        "pending_activestate_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("activestate_project_name", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization",
            "activestate_project_name",
            "actor_id",
            name="_pending_activestate_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_github_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("repository_name", sa.String(), nullable=False),
        sa.Column("repository_owner", sa.String(), nullable=False),
        sa.Column("repository_owner_id", sa.String(), nullable=False),
        sa.Column("workflow_filename", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            "environment",
            name="_pending_github_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_gitlab_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("workflow_filepath", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "namespace",
            "project",
            "workflow_filepath",
            "environment",
            name="_pending_gitlab_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_google_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("sub", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "sub", name="_pending_google_oidc_publisher_uc"),
    )
    op.create_table(
        "project_macaroon_warning_association",
        sa.Column("macaroon_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["macaroon_id"], ["macaroons.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("macaroon_id", "project_id", "id"),
    )
    op.create_table(
        "release_classifiers",
        sa.Column("trove_id", sa.Integer(), nullable=False),
        sa.Column("release_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trove_id"],
            ["trove_classifiers.id"],
        ),
        sa.PrimaryKeyConstraint("trove_id", "release_id"),
    )
    op.create_index(
        "rel_class_release_id_idx", "release_classifiers", ["release_id"], unique=False
    )
    op.create_index(
        "rel_class_trove_id_idx", "release_classifiers", ["trove_id"], unique=False
    )
    op.create_table(
        "release_dependencies",
        sa.Column("release_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Integer(), nullable=True),
        sa.Column("specifier", sa.String(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "release_dependencies_release_kind_idx",
        "release_dependencies",
        ["release_id", "kind"],
        unique=False,
    )
    op.create_table(
        "release_files",
        sa.Column("release_id", sa.UUID(), nullable=False),
        sa.Column("python_version", sa.String(), nullable=False),
        sa.Column("requires_python", sa.String(), nullable=True),
        sa.Column(
            "packagetype",
            postgresql.ENUM(
                "bdist_dmg",
                "bdist_dumb",
                "bdist_egg",
                "bdist_msi",
                "bdist_rpm",
                "bdist_wheel",
                "bdist_wininst",
                "sdist",
                name="packagetype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("comment_text", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("md5_digest", sa.String(), nullable=False),
        sa.Column("sha256_digest", postgresql.CITEXT(), nullable=False),
        sa.Column("blake2_256_digest", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "upload_time",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("uploaded_via", sa.String(), nullable=True),
        sa.Column("metadata_file_sha256_digest", postgresql.CITEXT(), nullable=True),
        sa.Column(
            "metadata_file_blake2_256_digest", postgresql.CITEXT(), nullable=True
        ),
        sa.Column(
            "allow_multiple_sdist",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "cached",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="If True, the object has been populated to our cache bucket.",
        ),
        sa.Column(
            "archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="If True, the object has been archived to our archival bucket.",
        ),
        sa.Column(
            "metadata_file_unbackfillable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
            comment="If True, the metadata for the file cannot be backfilled.",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint("blake2_256_digest ~* '^[A-F0-9]{64}$'"),
        sa.CheckConstraint("sha256_digest ~* '^[A-F0-9]{64}$'"),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blake2_256_digest"),
        sa.UniqueConstraint("filename"),
        sa.UniqueConstraint("md5_digest"),
        sa.UniqueConstraint("path"),
        sa.UniqueConstraint("sha256_digest"),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_release_files_requires_python()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
            BEGIN
                IF (TG_TABLE_NAME = 'releases') THEN
                    UPDATE
                        release_files
                    SET
                        requires_python = releases.requires_python
                    FROM releases
                    WHERE
                        release_files.release_id = releases.id
                            AND releases.id = NEW.id;
                ELSEIF (TG_TABLE_NAME = 'release_files') THEN
                    UPDATE
                        release_files
                    SET
                        requires_python = releases.requires_python
                    FROM releases
                    WHERE
                        release_files.release_id = releases.id
                            AND releases.id = NEW.release_id;
                END IF;

                RETURN NULL;
            END;
        $$
    """
    )
    op.execute(
        """
        CREATE TRIGGER release_files_requires_python
        AFTER INSERT ON release_files
        FOR EACH ROW
        EXECUTE FUNCTION update_release_files_requires_python()
    """
    )
    op.execute(
        """
        CREATE TRIGGER releases_requires_python
        AFTER INSERT OR UPDATE OF requires_python ON releases
        FOR EACH ROW
        EXECUTE FUNCTION update_release_files_requires_python()
    """
    )
    op.execute(
        """
        CREATE TRIGGER update_project_total_size_release_files
        AFTER INSERT OR DELETE OR UPDATE ON release_files
        FOR EACH ROW
        EXECUTE FUNCTION projects_total_size_release_files()
    """
    )
    op.create_index(
        "release_files_archived_idx", "release_files", ["archived"], unique=False
    )
    op.create_index(
        "release_files_cached_idx", "release_files", ["cached"], unique=False
    )
    op.create_index(
        "release_files_release_id_idx", "release_files", ["release_id"], unique=False
    )
    op.create_index(
        "release_files_single_sdist",
        "release_files",
        ["release_id", "packagetype"],
        unique=True,
        postgresql_where=sa.text(
            "packagetype = 'sdist' AND allow_multiple_sdist = false"
        ),
    )
    op.create_table(
        "release_observations",
        sa.Column(
            "related_id",
            sa.UUID(),
            nullable=True,
            comment="The ID of the related model",
        ),
        sa.Column(
            "related_name",
            sa.String(),
            nullable=False,
            comment="The name of the related model",
        ),
        sa.Column(
            "observer_id",
            sa.UUID(),
            nullable=False,
            comment="ID of the Observer who created the Observation",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="The time the observation was created",
        ),
        sa.Column(
            "kind", sa.String(), nullable=False, comment="The kind of observation"
        ),
        sa.Column(
            "summary",
            sa.String(),
            nullable=False,
            comment="A short summary of the observation",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="The observation payload we received",
        ),
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["observer_id"],
            ["observers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["related_id"],
            ["releases.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_release_observations_related_id"),
        "release_observations",
        ["related_id"],
        unique=False,
    )
    op.create_table(
        "release_urls",
        sa.Column("release_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column(
            "verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 32", name="release_urls_valid_name"
        ),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id", "name"),
    )
    op.create_index(
        op.f("ix_release_urls_release_id"), "release_urls", ["release_id"], unique=False
    )
    op.create_table(
        "release_vulnerabilities",
        sa.Column("release_id", sa.UUID(), nullable=False),
        sa.Column("vulnerability_source", sa.String(), nullable=False),
        sa.Column("vulnerability_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["vulnerability_source", "vulnerability_id"],
            ["vulnerabilities.source", "vulnerabilities.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("release_id"),
    )
    op.create_index(
        op.f("ix_release_vulnerabilities_release_id"),
        "release_vulnerabilities",
        ["release_id"],
        unique=False,
    )
    op.create_table(
        "stripe_subscription_items",
        sa.Column("subscription_item_id", sa.String(), nullable=True),
        sa.Column("subscription_id", sa.UUID(), nullable=False),
        sa.Column("subscription_price_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["stripe_subscriptions.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_price_id"],
            ["stripe_subscription_prices.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file_events",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["release_files.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_file_events_source_id", "file_events", ["source_id"], unique=False
    )
    op.create_table(
        "provenance",
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column(
            "provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["release_files.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("provenance")
    op.drop_index("ix_file_events_source_id", table_name="file_events")
    op.drop_table("file_events")
    op.drop_table("stripe_subscription_items")
    op.drop_index(
        op.f("ix_release_vulnerabilities_release_id"),
        table_name="release_vulnerabilities",
    )
    op.drop_table("release_vulnerabilities")
    op.drop_index(op.f("ix_release_urls_release_id"), table_name="release_urls")
    op.drop_table("release_urls")
    op.drop_index(
        op.f("ix_release_observations_related_id"), table_name="release_observations"
    )
    op.drop_table("release_observations")
    op.drop_index(
        "release_files_single_sdist",
        table_name="release_files",
        postgresql_where=sa.text(
            "packagetype = 'sdist' AND allow_multiple_sdist = false"
        ),
    )
    op.drop_index("release_files_release_id_idx", table_name="release_files")
    op.drop_index("release_files_cached_idx", table_name="release_files")
    op.drop_index("release_files_archived_idx", table_name="release_files")
    op.drop_table("release_files")
    op.drop_index(
        "release_dependencies_release_kind_idx", table_name="release_dependencies"
    )
    op.drop_table("release_dependencies")
    op.drop_index("rel_class_trove_id_idx", table_name="release_classifiers")
    op.drop_index("rel_class_release_id_idx", table_name="release_classifiers")
    op.drop_table("release_classifiers")
    op.drop_table("project_macaroon_warning_association")
    op.drop_table("pending_google_oidc_publishers")
    op.drop_table("pending_gitlab_oidc_publishers")
    op.drop_table("pending_github_oidc_publishers")
    op.drop_table("pending_activestate_oidc_publishers")
    op.drop_index(
        "organization_stripe_subscriptions_subscription_id_idx",
        table_name="organization_stripe_subscriptions",
    )
    op.drop_index(
        "organization_stripe_subscriptions_organization_id_idx",
        table_name="organization_stripe_subscriptions",
    )
    op.drop_table("organization_stripe_subscriptions")
    op.drop_index(
        op.f("ix_user_security_keys_user_id"), table_name="user_security_keys"
    )
    op.drop_table("user_security_keys")
    op.drop_index(
        op.f("ix_user_recovery_codes_user_id"), table_name="user_recovery_codes"
    )
    op.drop_table("user_recovery_codes")
    op.drop_index(
        op.f("ix_user_observations_related_id"), table_name="user_observations"
    )
    op.drop_table("user_observations")
    op.drop_index("ix_user_events_source_id", table_name="user_events")
    op.drop_table("user_events")
    op.drop_index("user_emails_user_id", table_name="user_emails")
    op.drop_table("user_emails")
    op.drop_index("team_roles_user_id_idx", table_name="team_roles")
    op.drop_index("team_roles_team_id_idx", table_name="team_roles")
    op.drop_table("team_roles")
    op.drop_index("team_project_roles_team_id_idx", table_name="team_project_roles")
    op.drop_index("team_project_roles_project_id_idx", table_name="team_project_roles")
    op.drop_table("team_project_roles")
    op.drop_index("ix_team_events_source_id", table_name="team_events")
    op.drop_table("team_events")
    op.drop_index(
        "stripe_subscriptions_subscription_id_idx", table_name="stripe_subscriptions"
    )
    op.drop_index(
        "stripe_subscriptions_stripe_customer_id_idx", table_name="stripe_subscriptions"
    )
    op.drop_table("stripe_subscriptions")
    op.drop_index("roles_user_id_idx", table_name="roles")
    op.drop_index("roles_project_id_idx", table_name="roles")
    op.drop_table("roles")
    op.drop_index("role_invitations_user_id_idx", table_name="role_invitations")
    op.drop_index(op.f("ix_role_invitations_user_id"), table_name="role_invitations")
    op.drop_index(op.f("ix_role_invitations_project_id"), table_name="role_invitations")
    op.drop_table("role_invitations")
    op.drop_index("release_version_idx", table_name="releases")
    op.drop_index("release_project_created_idx", table_name="releases")
    op.drop_index("release_created_idx", table_name="releases")
    op.drop_index("release_canonical_version_idx", table_name="releases")
    op.drop_index(op.f("ix_releases_uploader_id"), table_name="releases")
    op.drop_index(op.f("ix_releases_description_id"), table_name="releases")
    op.drop_table("releases")
    op.drop_index(
        op.f("ix_project_observations_related_id"), table_name="project_observations"
    )
    op.drop_table("project_observations")
    op.drop_index(
        op.f("ix_prohibited_user_names_prohibited_by"),
        table_name="prohibited_user_names",
    )
    op.drop_table("prohibited_user_names")
    op.drop_index(
        op.f("ix_prohibited_project_names_prohibited_by"),
        table_name="prohibited_project_names",
    )
    op.drop_table("prohibited_project_names")
    op.drop_index(
        op.f("ix_prohibited_email_domains_prohibited_by"),
        table_name="prohibited_email_domains",
    )
    op.drop_table("prohibited_email_domains")
    op.drop_index(
        "pending_project_name_ultranormalized", table_name="pending_oidc_publishers"
    )
    op.drop_index(
        op.f("ix_pending_oidc_publishers_added_by_id"),
        table_name="pending_oidc_publishers",
    )
    op.drop_table("pending_oidc_publishers")
    op.drop_index("organization_roles_user_id_idx", table_name="organization_roles")
    op.drop_index(
        "organization_roles_organization_id_idx", table_name="organization_roles"
    )
    op.drop_table("organization_roles")
    op.drop_index(
        "organization_invitations_user_id_idx", table_name="organization_invitations"
    )
    op.drop_index(
        op.f("ix_organization_invitations_user_id"),
        table_name="organization_invitations",
    )
    op.drop_index(
        op.f("ix_organization_invitations_organization_id"),
        table_name="organization_invitations",
    )
    op.drop_table("organization_invitations")
    op.drop_index(
        op.f("ix_organization_applications_submitted"),
        table_name="organization_applications",
    )
    op.drop_table("organization_applications")
    op.drop_index(op.f("ix_macaroons_user_id"), table_name="macaroons")
    op.drop_index(op.f("ix_macaroons_oidc_publisher_id"), table_name="macaroons")
    op.drop_table("macaroons")
    op.drop_index("journals_version_idx", table_name="journals")
    op.drop_index("journals_submitted_date_id_idx", table_name="journals")
    op.drop_index("journals_submitted_by_idx", table_name="journals")
    op.drop_index("journals_submitted_by_and_reverse_date_idx", table_name="journals")
    op.drop_index("journals_name_idx", table_name="journals")
    op.drop_index("journals_changelog", table_name="journals")
    op.drop_table("journals")
    op.drop_index(op.f("ix_users_sitemap_bucket"), table_name="users")
    op.drop_table("users")
    op.drop_index("teams_organization_id_idx", table_name="teams")
    op.drop_index(op.f("ix_teams_created"), table_name="teams")
    op.drop_table("teams")
    op.drop_table("stripe_subscription_prices")
    op.drop_index(op.f("ix_ses_events_event_id"), table_name="ses_events")
    op.drop_index(op.f("ix_ses_events_email_id"), table_name="ses_events")
    op.drop_table("ses_events")
    op.drop_index("ix_project_events_source_id", table_name="project_events")
    op.drop_table("project_events")
    op.drop_index(
        "organization_terms_of_service_agreements_organization_id_idx",
        table_name="organization_terms_of_service_agreements",
    )
    op.drop_table("organization_terms_of_service_agreements")
    op.drop_index(
        "organization_stripe_customers_stripe_customer_id_idx",
        table_name="organization_stripe_customers",
    )
    op.drop_index(
        "organization_stripe_customers_organization_id_idx",
        table_name="organization_stripe_customers",
    )
    op.drop_table("organization_stripe_customers")
    op.drop_index(
        "organization_projects_project_id_idx", table_name="organization_projects"
    )
    op.drop_index(
        "organization_projects_organization_id_idx", table_name="organization_projects"
    )
    op.drop_table("organization_projects")
    op.drop_index("ix_organization_events_source_id", table_name="organization_events")
    op.drop_table("organization_events")
    op.drop_table("oidc_publisher_project_association")
    op.drop_table("observers")
    op.drop_table("google_oidc_publishers")
    op.drop_table("gitlab_oidc_publishers")
    op.drop_table("github_oidc_publishers")
    op.drop_table("alternate_repositories")
    op.drop_table("activestate_oidc_publishers")
    op.drop_table("vulnerabilities")
    op.drop_table("trove_classifiers")
    op.drop_table("stripe_subscription_products")
    op.drop_table("stripe_customers")
    op.drop_table("sponsors")
    op.drop_index(op.f("ix_ses_emails_to"), table_name="ses_emails")
    op.drop_index(op.f("ix_ses_emails_message_id"), table_name="ses_emails")
    op.drop_table("ses_emails")
    op.drop_table("row_counts")
    op.drop_table("release_descriptions")
    op.drop_index("projects_lifecycle_status_idx", table_name="projects")
    op.drop_index("project_name_ultranormalized", table_name="projects")
    op.drop_index(op.f("ix_projects_sitemap_bucket"), table_name="projects")
    op.drop_index(op.f("ix_projects_created"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_organizations_created"), table_name="organizations")
    op.drop_table("organizations")
    op.drop_index(
        "organization_name_catalog_organization_id_idx",
        table_name="organization_name_catalog",
    )
    op.drop_index(
        "organization_name_catalog_normalized_name_idx",
        table_name="organization_name_catalog",
    )
    op.drop_index(
        op.f("ix_organization_name_catalog_organization_id"),
        table_name="organization_name_catalog",
    )
    op.drop_index(
        op.f("ix_organization_name_catalog_normalized_name"),
        table_name="organization_name_catalog",
    )
    op.drop_table("organization_name_catalog")
    op.drop_table("oidc_publishers")
    op.drop_table("observer_association")
    op.drop_index("bans_idx", table_name="ip_addresses")
    op.drop_table("ip_addresses")
    op.drop_table("file_registry")
    op.drop_table("banners")
    op.drop_table("admin_flags")
    sa.Enum("authentication-attempts", name="banreason").drop(op.get_bind())
    sa.Enum(
        "password compromised",
        "account frozen",
        "admin initiated",
        name="disablereason",
    ).drop(op.get_bind())
    sa.Enum(
        "spam complaint", "hard bounce", "soft bounce", name="unverifyreasons"
    ).drop(op.get_bind())
    sa.Enum(
        "Accepted",
        "Delivered",
        "Bounced",
        "Soft Bounced",
        "Complained",
        name="emailstatuses",
    ).drop(op.get_bind())
    sa.Enum("Delivery", "Bounce", "Complaint", name="eventtypes").drop(op.get_bind())
    sa.Enum(
        "Owner", "Billing Manager", "Manager", "Member", name="organizationroletype"
    ).drop(op.get_bind())
    sa.Enum("Community", "Company", name="organizationtype").drop(op.get_bind())
    sa.Enum("pending", "expired", name="organizationinvitationstatus").drop(
        op.get_bind()
    )
    sa.Enum("Member", name="teamroletype").drop(op.get_bind())
    sa.Enum("Owner", "Maintainer", name="teamprojectroletype").drop(op.get_bind())
    sa.Enum(
        "active",
        "past_due",
        "unpaid",
        "canceled",
        "incomplete",
        "incomplete_expired",
        "trialing",
        name="stripesubscriptionstatus",
    ).drop(op.get_bind())
    sa.Enum(
        "month", "year", "week", "day", name="stripesubscriptionpriceinterval"
    ).drop(op.get_bind())
    sa.Enum("pending", "expired", name="roleinvitationstatus").drop(op.get_bind())
    sa.Enum(
        "quarantine-enter", "quarantine-exit", "archived", name="lifecyclestatus"
    ).drop(op.get_bind())
    sa.Enum(
        "Platform",
        "Supported-Platform",
        "Summary",
        "Description",
        "Description-Content-Type",
        "Keywords",
        "Home-Page",
        "Download-Url",
        "Author",
        "Author-Email",
        "Maintainer",
        "Maintainer-Email",
        "License",
        "License-Expression",
        "License-File",
        "Classifier",
        "Requires-Dist",
        "Requires-Python",
        "Requires-External",
        "Project-Url",
        "Provides-Extra",
        "Provides-Dist",
        "Obsoletes-Dist",
        "Requires",
        "Provides",
        "Obsoletes",
        name="release_dynamic_fields",
    ).drop(op.get_bind())
    sa.Enum(
        "bdist_dmg",
        "bdist_dumb",
        "bdist_egg",
        "bdist_msi",
        "bdist_rpm",
        "bdist_wheel",
        "bdist_wininst",
        "sdist",
        name="packagetype",
    ).drop(op.get_bind())
    # ### end Alembic commands ###
