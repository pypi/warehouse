# SPDX-License-Identifier: Apache-2.0
"""
Initial Migration

Revision ID: 283c68f2ab2
Revises: None
Create Date: 2015-02-01 14:07:10.983672
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

revision = "283c68f2ab2"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "openid_discovered",
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=True),
        sa.Column("services", sa.LargeBinary(), nullable=True),
        sa.Column("op_endpoint", sa.Text(), nullable=True),
        sa.Column("op_local", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("url"),
    )

    op.create_table(
        "accounts_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("password", sa.String(length=128), nullable=False),
        sa.Column("last_login", sa.DateTime(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("username", CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_staff", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "date_joined", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
        sa.CheckConstraint(
            "username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="accounts_user_valid_username",
        ),
        sa.CheckConstraint("length(username) <= 50", name="packages_valid_name"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "packages",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("stable_version", sa.Text(), nullable=True),
        sa.Column("normalized_name", sa.Text(), nullable=True),
        sa.Column(
            "autohide", sa.Boolean(), server_default=sa.text("true"), nullable=True
        ),
        sa.Column(
            "comments", sa.Boolean(), server_default=sa.text("true"), nullable=True
        ),
        sa.Column("bugtrack_url", sa.Text(), nullable=True),
        sa.Column(
            "hosting_mode", sa.Text(), server_default="pypi-explicit", nullable=False
        ),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="packages_valid_name",
        ),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table("dual", sa.Column("dummy", sa.Integer(), nullable=True))

    op.create_table(
        "cheesecake_main_indices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("absolute", sa.Integer(), nullable=False),
        sa.Column("relative", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "trove_classifiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("classifier", sa.Text(), nullable=True),
        sa.Column("l2", sa.Integer(), nullable=True),
        sa.Column("l3", sa.Integer(), nullable=True),
        sa.Column("l4", sa.Integer(), nullable=True),
        sa.Column("l5", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("classifier", name="trove_classifiers_classifier_key"),
    )

    op.create_index(
        "trove_class_class_idx", "trove_classifiers", ["classifier"], unique=False
    )

    op.create_index("trove_class_id_idx", "trove_classifiers", ["id"], unique=False)

    op.create_table(
        "browse_tally",
        sa.Column("trove_id", sa.Integer(), nullable=False),
        sa.Column("tally", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("trove_id"),
    )

    op.create_table(
        "timestamps",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table(
        "oauth_nonce",
        sa.Column("timestamp", sa.Integer(), nullable=False),
        sa.Column("consumer", sa.String(length=32), nullable=False),
        sa.Column("nonce", sa.String(length=32), nullable=False),
        sa.Column("token", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "oid_associations",
        sa.Column("server_url", sa.String(length=2047), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=False),
        sa.Column("secret", sa.LargeBinary(length=128), nullable=False),
        sa.Column("issued", sa.Integer(), nullable=False),
        sa.Column("lifetime", sa.Integer(), nullable=False),
        sa.Column("assoc_type", sa.String(length=64), nullable=False),
        sa.CheckConstraint("length(secret) <= 128", name="secret_length_constraint"),
        sa.PrimaryKeyConstraint("server_url", "handle"),
    )

    op.create_table(
        "oid_nonces",
        sa.Column("server_url", sa.String(length=2047), nullable=False),
        sa.Column("timestamp", sa.Integer(), nullable=False),
        sa.Column("salt", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("server_url", "timestamp", "salt"),
    )

    op.create_table(
        "openid_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("assoc_handle", sa.Text(), nullable=True),
        sa.Column("expires", sa.DateTime(), nullable=True),
        sa.Column("mac_key", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "openid_nonces",
        sa.Column("created", sa.DateTime(), nullable=True),
        sa.Column("nonce", sa.Text(), nullable=True),
    )

    op.create_index("openid_nonces_created", "openid_nonces", ["created"], unique=False)

    op.create_index("openid_nonces_nonce", "openid_nonces", ["nonce"], unique=False)

    op.create_table(
        "file_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename", name="file_registry_filename_key"),
    )

    op.create_table(
        "openid_whitelist",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("trust_root", sa.Text(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("name", "trust_root"),
    )

    op.create_table(
        "releases",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("author_email", sa.Text(), nullable=True),
        sa.Column("maintainer", sa.Text(), nullable=True),
        sa.Column("maintainer_email", sa.Text(), nullable=True),
        sa.Column("home_page", sa.Text(), nullable=True),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("_pypi_ordering", sa.Integer(), nullable=True),
        sa.Column("_pypi_hidden", sa.Boolean(), nullable=True),
        sa.Column("description_html", sa.Text(), nullable=True),
        sa.Column("cheesecake_installability_id", sa.Integer(), nullable=True),
        sa.Column("cheesecake_documentation_id", sa.Integer(), nullable=True),
        sa.Column("cheesecake_code_kwalitee_id", sa.Integer(), nullable=True),
        sa.Column("requires_python", sa.Text(), nullable=True),
        sa.Column("description_from_readme", sa.Boolean(), nullable=True),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["cheesecake_code_kwalitee_id"], ["cheesecake_main_indices.id"]
        ),
        sa.ForeignKeyConstraint(
            ["cheesecake_documentation_id"], ["cheesecake_main_indices.id"]
        ),
        sa.ForeignKeyConstraint(
            ["cheesecake_installability_id"], ["cheesecake_main_indices.id"]
        ),
        sa.ForeignKeyConstraint(["name"], ["packages.name"], onupdate="CASCADE"),
        sa.PrimaryKeyConstraint("name", "version"),
    )

    op.create_index(
        "release_name_created_idx",
        "releases",
        ["name", sa.text("created DESC")],
        unique=False,
    )

    op.create_index("release_name_idx", "releases", ["name"], unique=False)

    op.create_index(
        "release_pypi_hidden_idx", "releases", ["_pypi_hidden"], unique=False
    )

    op.create_index("release_version_idx", "releases", ["version"], unique=False)

    op.create_table(
        "mirrors",
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("user_name", CITEXT(), nullable=True),
        sa.Column("index_url", sa.Text(), nullable=True),
        sa.Column("last_modified_url", sa.Text(), nullable=True),
        sa.Column("local_stats_url", sa.Text(), nullable=True),
        sa.Column("stats_url", sa.Text(), nullable=True),
        sa.Column("mirrors_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_name"], ["accounts_user.username"]),
        sa.PrimaryKeyConstraint("ip"),
    )

    op.create_table(
        "oauth_consumers",
        sa.Column("consumer", sa.String(length=32), nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column("date_created", sa.Date(), nullable=False),
        sa.Column("created_by", CITEXT(), nullable=True),
        sa.Column("last_modified", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["accounts_user.username"], onupdate="CASCADE"
        ),
        sa.PrimaryKeyConstraint("consumer"),
    )

    op.create_table(
        "accounts_email",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("primary", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["accounts_user.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="accounts_email_email_key"),
    )

    op.create_index(
        "accounts_email_email_like", "accounts_email", ["email"], unique=False
    )

    op.create_index(
        "accounts_email_user_id", "accounts_email", ["user_id"], unique=False
    )

    op.create_table(
        "oauth_access_tokens",
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column("consumer", sa.String(length=32), nullable=False),
        sa.Column("date_created", sa.Date(), nullable=False),
        sa.Column("last_modified", sa.Date(), nullable=False),
        sa.Column("user_name", CITEXT(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_name"],
            ["accounts_user.username"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token"),
    )

    op.create_table(
        "csrf_tokens",
        sa.Column("name", CITEXT(), nullable=False),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name"], ["accounts_user.username"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table(
        "oauth_request_tokens",
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column("consumer", sa.String(length=32), nullable=False),
        sa.Column("callback", sa.Text(), nullable=True),
        sa.Column("date_created", sa.Date(), nullable=False),
        sa.Column("user_name", CITEXT(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_name"],
            ["accounts_user.username"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token"),
    )

    op.create_table(
        "cookies",
        sa.Column("cookie", sa.Text(), nullable=False),
        sa.Column("name", CITEXT(), nullable=True),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name"], ["accounts_user.username"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("cookie"),
    )

    op.create_index("cookies_last_seen", "cookies", ["last_seen"], unique=False)

    op.create_table(
        "openids",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", CITEXT(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name"], ["accounts_user.username"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sshkeys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", CITEXT(), nullable=True),
        sa.Column("key", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name"], ["accounts_user.username"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("sshkeys_name", "sshkeys", ["name"], unique=False)

    op.create_table(
        "rego_otk",
        sa.Column("name", CITEXT(), nullable=True),
        sa.Column("otk", sa.Text(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name"], ["accounts_user.username"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("otk", name="rego_otk_unique"),
    )

    op.create_index("rego_otk_name_idx", "rego_otk", ["name"], unique=False)

    op.create_index("rego_otk_otk_idx", "rego_otk", ["otk"], unique=False)

    op.create_table(
        "cheesecake_subindices",
        sa.Column("main_index_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["main_index_id"], ["cheesecake_main_indices.id"]),
        sa.PrimaryKeyConstraint("main_index_id", "name"),
    )

    op.create_table(
        "accounts_gpgkey",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_id", CITEXT(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "key_id ~* '^[A-F0-9]{8}$'::citext", name="accounts_gpgkey_valid_key_id"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["accounts_user.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", name="accounts_gpgkey_key_id_key"),
    )

    op.create_index(
        "accounts_gpgkey_user_id", "accounts_gpgkey", ["user_id"], unique=False
    )

    op.create_table(
        "roles",
        sa.Column("role_name", sa.Text(), nullable=True),
        sa.Column("user_name", CITEXT(), nullable=True),
        sa.Column("package_name", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["package_name"], ["packages.name"], onupdate="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_name"], ["accounts_user.username"], onupdate="CASCADE"
        ),
    )

    op.create_index("roles_pack_name_idx", "roles", ["package_name"], unique=False)

    op.create_index("roles_user_name_idx", "roles", ["user_name"], unique=False)

    op.create_table(
        "journals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("submitted_date", sa.DateTime(), nullable=True),
        sa.Column("submitted_by", CITEXT(), nullable=True),
        sa.Column("submitted_from", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["submitted_by"], ["accounts_user.username"], onupdate="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "journals_changelog",
        "journals",
        ["submitted_date", "name", "version", "action"],
        unique=False,
    )

    op.create_index("journals_id_idx", "journals", ["id"], unique=False)

    op.create_index(
        "journals_latest_releases",
        "journals",
        ["submitted_date", "name", "version"],
        unique=False,
        postgresql_where=sa.text(
            "journals.version IS NOT NULL AND journals.action = 'new release'"
        ),
    )

    op.create_index("journals_name_idx", "journals", ["name"], unique=False)

    op.create_index("journals_version_idx", "journals", ["version"], unique=False)

    op.create_table(
        "ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("user_name", CITEXT(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_name"], ["accounts_user.username"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", "user_name", name="ratings_name_key"),
    )

    op.create_index("rating_name_version", "ratings", ["name", "version"], unique=False)

    op.create_table(
        "release_classifiers",
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("trove_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(["trove_id"], ["trove_classifiers.id"]),
    )

    op.create_index("rel_class_name_idx", "release_classifiers", ["name"], unique=False)

    op.create_index(
        "rel_class_name_version_idx",
        "release_classifiers",
        ["name", "version"],
        unique=False,
    )

    op.create_index(
        "rel_class_trove_id_idx", "release_classifiers", ["trove_id"], unique=False
    )

    op.create_index(
        "rel_class_version_id_idx", "release_classifiers", ["version"], unique=False
    )

    op.create_table(
        "release_urls",
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("packagetype", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),
    )

    op.create_index("release_urls_name_idx", "release_urls", ["name"], unique=False)

    op.create_index(
        "release_urls_packagetype_idx", "release_urls", ["packagetype"], unique=False
    )

    op.create_index(
        "release_urls_version_idx", "release_urls", ["version"], unique=False
    )

    op.create_table(
        "release_dependencies",
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("kind", sa.Integer(), nullable=True),
        sa.Column("specifier", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),
    )

    op.create_index("rel_dep_name_idx", "release_dependencies", ["name"], unique=False)

    op.create_index(
        "rel_dep_name_version_idx",
        "release_dependencies",
        ["name", "version"],
        unique=False,
    )

    op.create_index(
        "rel_dep_name_version_kind_idx",
        "release_dependencies",
        ["name", "version", "kind"],
        unique=False,
    )

    op.create_table(
        "comments_journal",
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=True),
        sa.Column("submitted_by", CITEXT(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"], ["accounts_user.username"], ondelete="CASCADE"
        ),
    )

    op.create_table(
        "release_files",
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("python_version", sa.Text(), nullable=True),
        sa.Column("packagetype", sa.Text(), nullable=True),
        sa.Column("comment_text", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("md5_digest", sa.Text(), nullable=True),
        sa.Column(
            "downloads", sa.Integer(), server_default=sa.text("0"), nullable=True
        ),
        sa.Column("upload_time", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),
        sa.UniqueConstraint("filename", name="release_files_filename_key"),
        sa.UniqueConstraint("md5_digest", name="release_files_md5_digest_key"),
    )

    op.create_index("release_files_name_idx", "release_files", ["name"], unique=False)

    op.create_index(
        "release_files_name_version_idx",
        "release_files",
        ["name", "version"],
        unique=False,
    )

    op.create_index(
        "release_files_packagetype_idx", "release_files", ["packagetype"], unique=False
    )

    op.create_index(
        "release_files_version_idx", "release_files", ["version"], unique=False
    )

    op.create_table(
        "release_requires_python",
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("specifier", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),
    )

    op.create_index(
        "rel_req_python_name_idx", "release_requires_python", ["name"], unique=False
    )

    op.create_index(
        "rel_req_python_name_version_idx",
        "release_requires_python",
        ["name", "version"],
        unique=False,
    )

    op.create_index(
        "rel_req_python_version_id_idx",
        "release_requires_python",
        ["version"],
        unique=False,
    )

    op.create_table(
        "description_urls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["name", "version"],
            ["releases.name", "releases.version"],
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "description_urls_name_idx", "description_urls", ["name"], unique=False
    )

    op.create_index(
        "description_urls_name_version_idx",
        "description_urls",
        ["name", "version"],
        unique=False,
    )

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("user_name", CITEXT(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("in_reply_to", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["in_reply_to"], ["comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rating"], ["ratings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_name"], ["accounts_user.username"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """ CREATE INDEX releases_name_ts_idx
            ON releases
            USING gin
            (to_tsvector('english'::regconfig, name))
        """
    )

    op.execute(
        """ CREATE INDEX releases_summary_ts_idx
            ON releases
            USING gin
            (to_tsvector('english'::regconfig, summary));
        """
    )


def downgrade():
    op.execute("DROP INDEX releases_summary_ts_idx")

    op.execute("DROP INDEX releases_name_ts_idx")

    op.drop_table("comments")

    op.drop_index("description_urls_name_version_idx", table_name="description_urls")

    op.drop_index("description_urls_name_idx", table_name="description_urls")

    op.drop_table("description_urls")

    op.drop_index("rel_req_python_version_id_idx", table_name="release_requires_python")

    op.drop_index(
        "rel_req_python_name_version_idx", table_name="release_requires_python"
    )

    op.drop_index("rel_req_python_name_idx", table_name="release_requires_python")

    op.drop_table("release_requires_python")

    op.drop_index("release_files_version_idx", table_name="release_files")

    op.drop_index("release_files_packagetype_idx", table_name="release_files")

    op.drop_index("release_files_name_version_idx", table_name="release_files")

    op.drop_index("release_files_name_idx", table_name="release_files")

    op.drop_table("release_files")

    op.drop_table("comments_journal")

    op.drop_index("rel_dep_name_version_kind_idx", table_name="release_dependencies")

    op.drop_index("rel_dep_name_version_idx", table_name="release_dependencies")

    op.drop_index("rel_dep_name_idx", table_name="release_dependencies")

    op.drop_table("release_dependencies")

    op.drop_index("release_urls_version_idx", table_name="release_urls")

    op.drop_index("release_urls_packagetype_idx", table_name="release_urls")

    op.drop_index("release_urls_name_idx", table_name="release_urls")

    op.drop_table("release_urls")

    op.drop_index("rel_class_version_id_idx", table_name="release_classifiers")

    op.drop_index("rel_class_trove_id_idx", table_name="release_classifiers")

    op.drop_index("rel_class_name_version_idx", table_name="release_classifiers")

    op.drop_index("rel_class_name_idx", table_name="release_classifiers")

    op.drop_table("release_classifiers")

    op.drop_index("rating_name_version", table_name="ratings")

    op.drop_table("ratings")

    op.drop_index("journals_version_idx", table_name="journals")

    op.drop_index("journals_name_idx", table_name="journals")

    op.drop_index("journals_latest_releases", table_name="journals")

    op.drop_index("journals_id_idx", table_name="journals")

    op.drop_index("journals_changelog", table_name="journals")

    op.drop_table("journals")

    op.drop_index("roles_user_name_idx", table_name="roles")

    op.drop_index("roles_pack_name_idx", table_name="roles")

    op.drop_table("roles")

    op.drop_index("accounts_gpgkey_user_id", table_name="accounts_gpgkey")

    op.drop_table("accounts_gpgkey")

    op.drop_table("cheesecake_subindices")

    op.drop_index("rego_otk_otk_idx", table_name="rego_otk")

    op.drop_index("rego_otk_name_idx", table_name="rego_otk")

    op.drop_table("rego_otk")

    op.drop_index("sshkeys_name", table_name="sshkeys")

    op.drop_table("sshkeys")

    op.drop_table("openids")

    op.drop_index("cookies_last_seen", table_name="cookies")

    op.drop_table("cookies")

    op.drop_table("oauth_request_tokens")

    op.drop_table("csrf_tokens")

    op.drop_table("oauth_access_tokens")

    op.drop_index("accounts_email_user_id", table_name="accounts_email")

    op.drop_index("accounts_email_email_like", table_name="accounts_email")

    op.drop_table("accounts_email")

    op.drop_table("oauth_consumers")

    op.drop_table("mirrors")

    op.drop_index("release_version_idx", table_name="releases")

    op.drop_index("release_pypi_hidden_idx", table_name="releases")

    op.drop_index("release_name_idx", table_name="releases")

    op.drop_index("release_name_created_idx", table_name="releases")

    op.drop_table("releases")

    op.drop_table("openid_whitelist")

    op.drop_table("file_registry")

    op.drop_index("openid_nonces_nonce", table_name="openid_nonces")

    op.drop_index("openid_nonces_created", table_name="openid_nonces")

    op.drop_table("openid_nonces")

    op.drop_table("openid_sessions")

    op.drop_table("oid_nonces")

    op.drop_table("oid_associations")

    op.drop_table("oauth_nonce")

    op.drop_table("timestamps")

    op.drop_table("browse_tally")

    op.drop_index("trove_class_id_idx", table_name="trove_classifiers")

    op.drop_index("trove_class_class_idx", table_name="trove_classifiers")

    op.drop_table("trove_classifiers")

    op.drop_table("cheesecake_main_indices")

    op.drop_table("dual")

    op.drop_table("packages")

    op.drop_table("accounts_user")

    op.drop_table("openid_discovered")
