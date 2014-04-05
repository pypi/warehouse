# Copyright 2013 Donald Stufft
#
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
Import initial database layout from PyPI

Revision ID: 77e04097be5
Revises: None
Create Date: 2013-09-22 15:11:30.966213
"""

# revision identifiers, used by Alembic.
revision = "77e04097be5"
down_revision = None

import sqlalchemy as sa

from alembic import op
from citext import CIText
from sqlalchemy.dialects.postgresql import BYTEA


def upgrade():
    op.create_table("timestamps",
        sa.Column("name", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("value", sa.TIMESTAMP()),
    )

    op.create_table("accounts_user",
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
        sa.Column("password", sa.VARCHAR(length=128), nullable=False),
        sa.Column("last_login", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("is_superuser", sa.BOOLEAN(), nullable=False),
        sa.Column("username", CIText(), nullable=False, unique=True),
        sa.Column("name", sa.VARCHAR(length=100), nullable=False),
        sa.Column("is_staff", sa.BOOLEAN(), nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), nullable=False),
        sa.Column("date_joined", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_check_constraint("accounts_user_username_length",
        "accounts_user",
        sa.text("length(username) <= 50"),
    )

    op.create_check_constraint("accounts_user_valid_username",
        "accounts_user",
        sa.text("username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'"),
    )

    op.create_table("cookies",
        sa.Column("cookie", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("name",
            CIText(),
            sa.ForeignKey("accounts_user.username",
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),
        ),
        sa.Column("last_seen", sa.TIMESTAMP()),
    )

    op.create_index("cookies_last_seen", "cookies", ["last_seen"])

    op.create_table("oauth_consumers",
        sa.Column("consumer",
            sa.VARCHAR(length=32),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("secret", sa.VARCHAR(length=64), nullable=False),
        sa.Column("date_created", sa.DATE(), nullable=False),
        sa.Column("created_by",
            CIText(),
            sa.ForeignKey("accounts_user.username", onupdate="CASCADE"),
        ),
        sa.Column("last_modified", sa.DATE(), nullable=False),
        sa.Column("description", sa.VARCHAR(length=255), nullable=False),
    )

    op.create_table("cheesecake_main_indices",
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
        sa.Column("absolute", sa.INTEGER(), nullable=False),
        sa.Column("relative", sa.INTEGER(), nullable=False),
    )

    op.create_table("packages",
        sa.Column("name", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("stable_version", sa.TEXT()),
        sa.Column("normalized_name", sa.TEXT()),
        sa.Column("autohide", sa.BOOLEAN(), server_default=sa.text("TRUE")),
        sa.Column("comments", sa.BOOLEAN(), server_default=sa.text("TRUE")),
        sa.Column("bugtrack_url", sa.TEXT()),
        sa.Column("hosting_mode", sa.TEXT(),
            nullable=False,
            server_default="pypi-explicit",
        ),
    )

    op.create_check_constraint("packages_valid_name",
        "packages",
        sa.text("name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'"),
    )

    op.create_table("releases",
        sa.Column("name",
            sa.TEXT(),
            sa.ForeignKey("packages.name", onupdate="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("version", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("author", sa.TEXT()),
        sa.Column("author_email", sa.TEXT()),
        sa.Column("maintainer", sa.TEXT()),
        sa.Column("maintainer_email", sa.TEXT()),
        sa.Column("home_page", sa.TEXT()),
        sa.Column("license", sa.TEXT()),
        sa.Column("summary", sa.TEXT()),
        sa.Column("description", sa.TEXT()),
        sa.Column("keywords", sa.TEXT()),
        sa.Column("platform", sa.TEXT()),
        sa.Column("download_url", sa.TEXT()),
        sa.Column("_pypi_ordering", sa.INTEGER()),
        sa.Column("_pypi_hidden", sa.BOOLEAN()),
        sa.Column("description_html", sa.TEXT()),
        sa.Column("cheesecake_installability_id",
            sa.INTEGER(),
            sa.ForeignKey("cheesecake_main_indices.id"),
        ),
        sa.Column("cheesecake_documentation_id",
            sa.INTEGER(),
            sa.ForeignKey("cheesecake_main_indices.id"),
        ),
        sa.Column("cheesecake_code_kwalitee_id",
            sa.INTEGER(),
            sa.ForeignKey("cheesecake_main_indices.id"),
        ),
        sa.Column("requires_python", sa.TEXT()),
        sa.Column("description_from_readme", sa.BOOLEAN()),
    )

    op.create_index("release_name_idx", "releases", ["name"])

    op.create_index("release_version_idx", "releases", ["version"])

    op.create_index("release_pypi_hidden_idx", "releases", ["_pypi_hidden"])

    op.create_table("release_dependencies",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("kind", sa.INTEGER()),
        sa.Column("specifier", sa.TEXT()),
    )

    op.create_index("rel_dep_name_idx", "release_dependencies", ["name"])

    op.create_index("rel_dep_name_version_idx",
        "release_dependencies",
        ["name", "version"],
    )

    op.create_index("rel_dep_name_version_kind_idx",
        "release_dependencies",
        ["name", "version", "kind"],
    )

    op.create_foreign_key(
        None,
        "release_dependencies",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )

    op.create_table("ratings",
        sa.Column("name", sa.TEXT(), nullable=False),
        sa.Column("version", sa.TEXT(), nullable=False),
        sa.Column("user_name",
            CIText(),
            sa.ForeignKey("accounts_user.username", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.TIMESTAMP()),
        sa.Column("rating", sa.INTEGER()),
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
    )

    op.create_unique_constraint("ratings_id_key", "ratings", ["id"])

    op.create_unique_constraint("ratings_name_key",
        "ratings",
        ["name", "version", "user_name"],
    )

    op.create_foreign_key(
        None,
        "ratings",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )

    op.create_index("rating_name_version", "ratings", ["name", "version"])

    op.create_table("comments",
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
        sa.Column("rating",
            sa.INTEGER(),
            sa.ForeignKey("ratings.id",
                ondelete="CASCADE",
            ),
        ),
        sa.Column("user_name",
            CIText(),
            sa.ForeignKey("accounts_user.username", ondelete="CASCADE"),
        ),
        sa.Column("date", sa.TIMESTAMP()),
        sa.Column("message", sa.TEXT()),
        sa.Column("in_reply_to",
            sa.INTEGER(),
            sa.ForeignKey("comments.id",
                ondelete="CASCADE",
            ),
        ),
    )

    op.create_table("oauth_access_tokens",
        sa.Column("token",
            sa.VARCHAR(length=32),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("secret", sa.VARCHAR(length=64), nullable=False),
        sa.Column("consumer", sa.VARCHAR(length=32), nullable=False),
        sa.Column("date_created", sa.DATE(), nullable=False),
        sa.Column("last_modified", sa.DATE(), nullable=False),
        sa.Column("user_name",
            CIText(),
            sa.ForeignKey("accounts_user.username",
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),
        ),
    )

    op.create_table("openid_nonces",
        sa.Column("created", sa.TIMESTAMP()),
        sa.Column("nonce", sa.TEXT()),
    )

    op.create_index("openid_nonces_created", "openid_nonces", ["created"])

    op.create_index("openid_nonces_nonce", "openid_nonces", ["nonce"])

    op.create_table("openid_sessions",
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
        sa.Column("url", sa.TEXT()),
        sa.Column("assoc_handle", sa.TEXT()),
        sa.Column("expires", sa.TIMESTAMP()),
        sa.Column("mac_key", sa.TEXT()),
    )

    op.create_table("oauth_request_tokens",
        sa.Column("token",
            sa.VARCHAR(length=32),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("secret", sa.VARCHAR(length=64), nullable=False),
        sa.Column("consumer", sa.VARCHAR(length=32), nullable=False),
        sa.Column("callback", sa.TEXT()),
        sa.Column("date_created", sa.DATE(), nullable=False),
        sa.Column("user_name",
            CIText(),
            sa.ForeignKey("accounts_user.username",
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),
        ),
    )

    op.create_table("oid_nonces",
        sa.Column("server_url",
            sa.VARCHAR(length=2047),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("timestamp",
            sa.INTEGER(),
            autoincrement=False,
            primary_key=True,
            nullable=False,
        ),
        sa.Column("salt",
            sa.CHAR(length=40),
            primary_key=True,
            nullable=False,
        ),
    )

    op.create_table("mirrors",
        sa.Column("ip", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("user_name",
            CIText(),
            sa.ForeignKey("accounts_user.username"),
        ),
        sa.Column("index_url", sa.TEXT()),
        sa.Column("last_modified_url", sa.TEXT()),
        sa.Column("local_stats_url", sa.TEXT()),
        sa.Column("stats_url", sa.TEXT()),
        sa.Column("mirrors_url", sa.TEXT()),
    )

    op.create_table("trove_classifiers",
        sa.Column("id",
            sa.INTEGER(),
            autoincrement=False,
            primary_key=True,
            nullable=False,
        ),
        sa.Column("classifier", sa.TEXT()),
        sa.Column("l2", sa.INTEGER()),
        sa.Column("l3", sa.INTEGER()),
        sa.Column("l4", sa.INTEGER()),
        sa.Column("l5", sa.INTEGER()),
    )

    op.create_index("trove_class_class_idx",
        "trove_classifiers",
        ["classifier"],
    )

    op.create_index("trove_class_id_idx", "trove_classifiers", ["id"])

    op.create_unique_constraint("trove_classifiers_classifier_key",
        "trove_classifiers",
        ["classifier"],
    )

    op.create_table("roles",
        sa.Column("role_name", sa.TEXT()),
        sa.Column("user_name",
            CIText(),
            sa.ForeignKey("accounts_user.username", onupdate="CASCADE"),
        ),
        sa.Column("package_name",
            sa.TEXT(),
            sa.ForeignKey("packages.name", onupdate="CASCADE"),
        ),
    )

    op.create_index("roles_pack_name_idx", "roles", ["package_name"])

    op.create_index("roles_user_name_idx", "roles", ["user_name"])

    op.create_table("release_requires_python",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("specifier", sa.TEXT()),
    )

    op.create_foreign_key(
        None,
        "release_requires_python",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )

    op.create_index("rel_req_python_name_idx",
        "release_requires_python",
        ["name"],
    )

    op.create_index("rel_req_python_name_version_idx",
        "release_requires_python",
        ["name", "version"],
    )

    op.create_index("rel_req_python_version_id_idx",
        "release_requires_python",
        ["version"],
    )

    op.create_table("browse_tally",
        sa.Column("trove_id",
            sa.INTEGER(),
            autoincrement=False,
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tally", sa.INTEGER()),
    )

    op.create_table("dual",
        sa.Column("dummy", sa.INTEGER()),
    )

    op.create_table("release_urls",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("url", sa.TEXT()),
        sa.Column("packagetype", sa.TEXT()),
    )

    op.create_foreign_key(
        None,
        "release_urls",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )

    op.create_index("release_urls_name_idx", "release_urls", ["name"])

    op.create_index("release_urls_packagetype_idx",
        "release_urls",
        ["packagetype"],
    )

    op.create_index("release_urls_version_idx", "release_urls", ["version"])

    op.create_table("description_urls",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("url", sa.TEXT()),
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
    )

    op.create_index("description_urls_name_idx", "description_urls", ["name"])

    op.create_index("description_urls_name_version_idx",
        "description_urls",
        ["name", "version"],
    )

    op.create_foreign_key(
        None,
        "description_urls",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )

    op.create_table("oauth_nonce",
        sa.Column("timestamp", sa.INTEGER(), nullable=False),
        sa.Column("consumer", sa.VARCHAR(length=32), nullable=False),
        sa.Column("nonce", sa.VARCHAR(length=32), nullable=False),
        sa.Column("token", sa.VARCHAR(length=32)),
    )

    op.create_table("journals",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("action", sa.TEXT()),
        sa.Column("submitted_date", sa.TIMESTAMP()),
        sa.Column("submitted_by",
            CIText(),
            sa.ForeignKey("accounts_user.username", onupdate="CASCADE"),
        ),
        sa.Column("submitted_from", sa.TEXT()),
    )
    op.execute("ALTER TABLE journals ADD COLUMN id SERIAL")

    op.create_index("journals_name_idx", "journals", ["name"])

    op.create_index("journals_changelog",
        "journals",
        ["submitted_date", "name", "version", "action"],
    )

    op.create_index("journals_latest_releases",
        "journals",
        ["submitted_date", "name", "version"],
    )

    op.create_index("journals_version_idx", "journals", ["version"])

    op.create_table("rego_otk",
        sa.Column("name",
            CIText(),
            sa.ForeignKey("accounts_user.username", ondelete="CASCADE"),
        ),
        sa.Column("otk", sa.TEXT()),
        sa.Column("date", sa.TIMESTAMP()),
    )

    op.create_index("rego_otk_otk_idx", "rego_otk", ["otk"])

    op.create_index("rego_otk_name_idx", "rego_otk", ["name"])

    op.create_unique_constraint("rego_otk_unique", "rego_otk", ["otk"])

    op.create_table("release_files",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("python_version", sa.TEXT()),
        sa.Column("packagetype", sa.TEXT()),
        sa.Column("comment_text", sa.TEXT()),
        sa.Column("filename", sa.TEXT()),
        sa.Column("md5_digest", sa.TEXT()),
        sa.Column("downloads", sa.INTEGER(), server_default=sa.text("0")),
        sa.Column("upload_time", sa.TIMESTAMP()),
    )

    op.create_index("release_files_name_idx", "release_files", ["name"])

    op.create_index("release_files_name_version_idx",
        "release_files",
        ["name", "version"],
    )

    op.create_index("release_files_version_idx", "release_files", ["version"])

    op.create_index("release_files_packagetype_idx",
        "release_files",
        ["packagetype"],
    )

    op.create_unique_constraint("release_files_filename_key",
        "release_files",
        ["filename"],
    )

    op.create_unique_constraint("release_files_md5_digest_key",
        "release_files",
        ["md5_digest"],
    )

    op.create_foreign_key(
        None,
        "release_files",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )

    op.create_table("openid_whitelist",
        sa.Column("name", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("trust_root", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("created", sa.TIMESTAMP()),
    )

    op.create_table("comments_journal",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("id", sa.INTEGER()),
        sa.Column("submitted_by",
            CIText(),
            sa.ForeignKey("accounts_user.username", ondelete="CASCADE"),
        ),
        sa.Column("date", sa.TIMESTAMP()),
        sa.Column("action", sa.TEXT()),
    )

    op.create_foreign_key(
        None,
        "comments_journal",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )

    op.create_table("csrf_tokens",
        sa.Column("name",
            CIText(),
            sa.ForeignKey("accounts_user.username",
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("token", sa.TEXT()),
        sa.Column("end_date", sa.TIMESTAMP()),
    )

    op.create_table("oid_associations",
        sa.Column("server_url",
            sa.VARCHAR(length=2047),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("handle",
            sa.VARCHAR(length=255),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("secret", BYTEA(), nullable=False),
        sa.Column("issued", sa.INTEGER(), nullable=False),
        sa.Column("lifetime", sa.INTEGER(), nullable=False),
        sa.Column("assoc_type", sa.VARCHAR(length=64), nullable=False),
    )

    op.create_check_constraint("secret_length_constraint",
        "oid_associations",
        sa.text("length(secret) <= 128"),
    )

    op.create_table("cheesecake_subindices",
        sa.Column("main_index_id",
            sa.INTEGER(),
            sa.ForeignKey("cheesecake_main_indices.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("value", sa.INTEGER(), nullable=False),
        sa.Column("details", sa.TEXT(), nullable=False),
    )

    op.create_table("accounts_email",
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
        sa.Column("user_id",
            sa.INTEGER(),
            sa.ForeignKey("accounts_user.id",
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=False,
        ),
        sa.Column("email", sa.VARCHAR(length=254), nullable=False),
        sa.Column("primary", sa.BOOLEAN(), nullable=False),
        sa.Column("verified", sa.BOOLEAN(), nullable=False),
    )

    op.create_index("accounts_email_email_like", "accounts_email", ["email"])

    op.create_index("accounts_email_user_id", "accounts_email", ["user_id"])

    op.create_unique_constraint("accounts_email_email_key",
        "accounts_email",
        ["email"],
    )

    op.create_table("sshkeys",
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
        sa.Column("name",
            CIText(),
            sa.ForeignKey("accounts_user.username",
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),
        ),
        sa.Column("key", sa.TEXT()),
    )

    op.create_index("sshkeys_name", "sshkeys", ["name"])

    op.create_table("accounts_gpgkey",
        sa.Column("id", sa.INTEGER(), primary_key=True, nullable=False),
        sa.Column("user_id",
            sa.INTEGER(),
            sa.ForeignKey("accounts_user.id",
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=False,
        ),
        sa.Column("key_id", CIText(), nullable=False),
        sa.Column("verified", sa.BOOLEAN(), nullable=False),
    )

    op.create_unique_constraint("accounts_gpgkey_key_id_key",
        "accounts_gpgkey",
        ["key_id"],
    )

    op.create_check_constraint("accounts_gpgkey_valid_key_id",
        "accounts_gpgkey",
        sa.text("key_id ~* '^[A-F0-9]{8}$'"),
    )

    op.create_index("accounts_gpgkey_user_id", "accounts_gpgkey", ["user_id"])

    op.create_table("openid_discovered",
        sa.Column("created", sa.TIMESTAMP()),
        sa.Column("url", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("services", BYTEA()),
        sa.Column("op_endpoint", sa.TEXT()),
        sa.Column("op_local", sa.TEXT()),
    )

    op.create_table("release_classifiers",
        sa.Column("name", sa.TEXT()),
        sa.Column("version", sa.TEXT()),
        sa.Column("trove_id",
            sa.INTEGER(),
            sa.ForeignKey("trove_classifiers.id"),
        ),
    )

    op.create_index("rel_class_name_idx", "release_classifiers", ["name"])

    op.create_index("rel_class_name_version_idx",
        "release_classifiers",
        ["name", "version"],
    )

    op.create_index("rel_class_version_id_idx",
        "release_classifiers",
        ["version"],
    )

    op.create_index("rel_class_trove_id_idx",
        "release_classifiers",
        ["trove_id"],
    )

    op.create_foreign_key(
        None,
        "release_classifiers",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )

    op.create_table("openids",
        sa.Column("id", sa.TEXT(), primary_key=True, nullable=False),
        sa.Column("name",
            CIText(),
            sa.ForeignKey("accounts_user.username",
                onupdate="CASCADE",
                ondelete="CASCADE",
            ),
        ),
    )


def downgrade():
    op.drop_table("openids")
    op.drop_table("release_classifiers")
    op.drop_table("openid_discovered")
    op.drop_table("accounts_gpgkey")
    op.drop_table("sshkeys")
    op.drop_table("accounts_email")
    op.drop_table("cheesecake_subindices")
    op.drop_table("oid_associations")
    op.drop_table("csrf_tokens")
    op.drop_table("comments_journal")
    op.drop_table("openid_whitelist")
    op.drop_table("release_files")
    op.drop_table("rego_otk")
    op.drop_table("journals")
    op.drop_table("oauth_nonce")
    op.drop_table("description_urls")
    op.drop_table("release_urls")
    op.drop_table("dual")
    op.drop_table("browse_tally")
    op.drop_table("release_requires_python")
    op.drop_table("roles")
    op.drop_table("trove_classifiers")
    op.drop_table("mirrors")
    op.drop_table("oid_nonces")
    op.drop_table("oauth_request_tokens")
    op.drop_table("openid_sessions")
    op.drop_table("openid_nonces")
    op.drop_table("oauth_access_tokens")
    op.drop_table("comments")
    op.drop_table("ratings")
    op.drop_table("release_dependencies")
    op.drop_table("releases")
    op.drop_table("packages")
    op.drop_table("cheesecake_main_indices")
    op.drop_table("oauth_consumers")
    op.drop_table("cookies")
    op.drop_table("accounts_user")
    op.drop_table("timestamps")
