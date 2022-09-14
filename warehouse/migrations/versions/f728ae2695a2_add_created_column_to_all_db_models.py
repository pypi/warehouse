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
Add 'created' column to all DB models

Revision ID: f728ae2695a2
Revises: 7eaad728b806
Create Date: 2022-09-14 16:57:28.024958
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f728ae2695a2"
down_revision = "7eaad728b806"


def upgrade():
    op.add_column(
        "banners",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(op.f("ix_banners_created"), "banners", ["created"], unique=False)
    op.alter_column(
        "macaroons",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(
        op.f("ix_macaroons_created"), "macaroons", ["created"], unique=False
    )
    op.alter_column(
        "malware_checks",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(
        op.f("ix_malware_checks_created"), "malware_checks", ["created"], unique=False
    )
    op.add_column(
        "malware_verdicts",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_malware_verdicts_created"),
        "malware_verdicts",
        ["created"],
        unique=False,
    )
    op.add_column(
        "oidc_provider_project_association",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_oidc_provider_project_association_created"),
        "oidc_provider_project_association",
        ["created"],
        unique=False,
    )
    op.add_column(
        "oidc_providers",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_oidc_providers_created"), "oidc_providers", ["created"], unique=False
    )
    op.add_column(
        "organization_events",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_organization_events_created"),
        "organization_events",
        ["created"],
        unique=False,
    )
    op.add_column(
        "organization_invitations",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_organization_invitations_created"),
        "organization_invitations",
        ["created"],
        unique=False,
    )
    op.add_column(
        "organization_name_catalog",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_organization_name_catalog_created"),
        "organization_name_catalog",
        ["created"],
        unique=False,
    )
    op.add_column(
        "organization_project",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_organization_project_created"),
        "organization_project",
        ["created"],
        unique=False,
    )
    op.add_column(
        "organization_roles",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_organization_roles_created"),
        "organization_roles",
        ["created"],
        unique=False,
    )
    op.alter_column(
        "organizations",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "prohibited_project_names",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(
        op.f("ix_prohibited_project_names_created"),
        "prohibited_project_names",
        ["created"],
        unique=False,
    )
    op.alter_column(
        "prohibited_user_names",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(
        op.f("ix_prohibited_user_names_created"),
        "prohibited_user_names",
        ["created"],
        unique=False,
    )
    op.add_column(
        "project_events",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_project_events_created"), "project_events", ["created"], unique=False
    )
    op.alter_column(
        "projects",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.add_column(
        "release_dependencies",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_release_dependencies_created"),
        "release_dependencies",
        ["created"],
        unique=False,
    )
    op.add_column(
        "release_descriptions",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_release_descriptions_created"),
        "release_descriptions",
        ["created"],
        unique=False,
    )
    op.add_column(
        "release_files",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_release_files_created"), "release_files", ["created"], unique=False
    )
    op.add_column(
        "release_urls",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_release_urls_created"), "release_urls", ["created"], unique=False
    )
    op.alter_column(
        "releases",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(op.f("ix_releases_created"), "releases", ["created"], unique=False)
    op.add_column(
        "role_invitations",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_role_invitations_created"),
        "role_invitations",
        ["created"],
        unique=False,
    )
    op.add_column(
        "roles",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(op.f("ix_roles_created"), "roles", ["created"], unique=False)
    op.add_column(
        "row_counts",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_row_counts_created"), "row_counts", ["created"], unique=False
    )
    op.alter_column(
        "ses_emails",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(
        op.f("ix_ses_emails_created"), "ses_emails", ["created"], unique=False
    )
    op.alter_column(
        "ses_events",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(
        op.f("ix_ses_events_created"), "ses_events", ["created"], unique=False
    )
    op.add_column(
        "sponsors",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(op.f("ix_sponsors_created"), "sponsors", ["created"], unique=False)
    op.add_column(
        "team_events",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_team_events_created"), "team_events", ["created"], unique=False
    )
    op.add_column(
        "team_project_roles",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_team_project_roles_created"),
        "team_project_roles",
        ["created"],
        unique=False,
    )
    op.add_column(
        "team_roles",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_team_roles_created"), "team_roles", ["created"], unique=False
    )
    op.alter_column(
        "teams",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.add_column(
        "user_events",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_user_events_created"), "user_events", ["created"], unique=False
    )
    op.add_column(
        "user_recovery_codes",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_user_recovery_codes_created"),
        "user_recovery_codes",
        ["created"],
        unique=False,
    )
    op.add_column(
        "user_security_keys",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_user_security_keys_created"),
        "user_security_keys",
        ["created"],
        unique=False,
    )
    op.alter_column(
        "user_titan_codes",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_index(
        op.f("ix_user_titan_codes_created"),
        "user_titan_codes",
        ["created"],
        unique=False,
    )
    op.add_column(
        "users",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(op.f("ix_users_created"), "users", ["created"], unique=False)
    op.add_column(
        "vulnerabilities",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    op.create_index(
        op.f("ix_vulnerabilities_created"), "vulnerabilities", ["created"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_vulnerabilities_created"), table_name="vulnerabilities")
    op.drop_column("vulnerabilities", "created")
    op.drop_index(op.f("ix_users_created"), table_name="users")
    op.drop_column("users", "created")
    op.drop_index(op.f("ix_user_titan_codes_created"), table_name="user_titan_codes")
    op.alter_column(
        "user_titan_codes",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(
        op.f("ix_user_security_keys_created"), table_name="user_security_keys"
    )
    op.drop_column("user_security_keys", "created")
    op.drop_index(
        op.f("ix_user_recovery_codes_created"), table_name="user_recovery_codes"
    )
    op.drop_column("user_recovery_codes", "created")
    op.drop_index(op.f("ix_user_events_created"), table_name="user_events")
    op.drop_column("user_events", "created")
    op.alter_column(
        "teams",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_team_roles_created"), table_name="team_roles")
    op.drop_column("team_roles", "created")
    op.drop_index(
        op.f("ix_team_project_roles_created"), table_name="team_project_roles"
    )
    op.drop_column("team_project_roles", "created")
    op.drop_index(op.f("ix_team_events_created"), table_name="team_events")
    op.drop_column("team_events", "created")
    op.drop_index(op.f("ix_sponsors_created"), table_name="sponsors")
    op.drop_column("sponsors", "created")
    op.drop_index(op.f("ix_ses_events_created"), table_name="ses_events")
    op.alter_column(
        "ses_events",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_ses_emails_created"), table_name="ses_emails")
    op.alter_column(
        "ses_emails",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_row_counts_created"), table_name="row_counts")
    op.drop_column("row_counts", "created")
    op.drop_index(op.f("ix_roles_created"), table_name="roles")
    op.drop_column("roles", "created")
    op.drop_index(op.f("ix_role_invitations_created"), table_name="role_invitations")
    op.drop_column("role_invitations", "created")
    op.drop_index(op.f("ix_releases_created"), table_name="releases")
    op.alter_column(
        "releases",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_release_urls_created"), table_name="release_urls")
    op.drop_column("release_urls", "created")
    op.drop_index(op.f("ix_release_files_created"), table_name="release_files")
    op.drop_column("release_files", "created")
    op.drop_index(
        op.f("ix_release_descriptions_created"), table_name="release_descriptions"
    )
    op.drop_column("release_descriptions", "created")
    op.drop_index(
        op.f("ix_release_dependencies_created"), table_name="release_dependencies"
    )
    op.drop_column("release_dependencies", "created")
    op.alter_column(
        "projects",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_project_events_created"), table_name="project_events")
    op.drop_column("project_events", "created")
    op.drop_index(
        op.f("ix_prohibited_user_names_created"), table_name="prohibited_user_names"
    )
    op.alter_column(
        "prohibited_user_names",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(
        op.f("ix_prohibited_project_names_created"),
        table_name="prohibited_project_names",
    )
    op.alter_column(
        "prohibited_project_names",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "organizations",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(
        op.f("ix_organization_roles_created"), table_name="organization_roles"
    )
    op.drop_column("organization_roles", "created")
    op.drop_index(
        op.f("ix_organization_project_created"), table_name="organization_project"
    )
    op.drop_column("organization_project", "created")
    op.drop_index(
        op.f("ix_organization_name_catalog_created"),
        table_name="organization_name_catalog",
    )
    op.drop_column("organization_name_catalog", "created")
    op.drop_index(
        op.f("ix_organization_invitations_created"),
        table_name="organization_invitations",
    )
    op.drop_column("organization_invitations", "created")
    op.drop_index(
        op.f("ix_organization_events_created"), table_name="organization_events"
    )
    op.drop_column("organization_events", "created")
    op.drop_index(op.f("ix_oidc_providers_created"), table_name="oidc_providers")
    op.drop_column("oidc_providers", "created")
    op.drop_index(
        op.f("ix_oidc_provider_project_association_created"),
        table_name="oidc_provider_project_association",
    )
    op.drop_column("oidc_provider_project_association", "created")
    op.drop_index(op.f("ix_malware_verdicts_created"), table_name="malware_verdicts")
    op.drop_column("malware_verdicts", "created")
    op.drop_index(op.f("ix_malware_checks_created"), table_name="malware_checks")
    op.alter_column(
        "malware_checks",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_macaroons_created"), table_name="macaroons")
    op.alter_column(
        "macaroons",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.drop_index(op.f("ix_banners_created"), table_name="banners")
    op.drop_column("banners", "created")
