# SPDX-License-Identifier: Apache-2.0
"""
Remove no longer needed tables

Revision ID: f2a453c96ded
Revises: e0ca60b6a30b
Create Date: 2018-05-17 13:42:01.529533
"""

from alembic import op

revision = "f2a453c96ded"
down_revision = "e0ca60b6a30b"


def upgrade():
    op.drop_table("oid_nonces")
    op.drop_table("oauth_access_tokens")
    op.drop_index("accounts_gpgkey_user_id", table_name="accounts_gpgkey")
    op.drop_table("accounts_gpgkey")
    op.drop_index("cookies_last_seen", table_name="cookies")
    op.drop_table("cookies")
    op.drop_table("openid_discovered")
    op.drop_index("openids_subkey", table_name="openids")
    op.drop_table("openids")
    op.drop_table("csrf_tokens")
    op.drop_index("description_urls_name_idx", table_name="description_urls")
    op.drop_index("description_urls_name_version_idx", table_name="description_urls")
    op.drop_table("description_urls")
    op.drop_table("mirrors")
    op.drop_table("oauth_nonce")
    op.drop_table("oauth_request_tokens")
    op.drop_table("browse_tally")
    op.drop_table("comments_journal")
    op.drop_table("timestamps")
    op.drop_index("rating_name_version", table_name="ratings")
    op.drop_table("dual")
    op.drop_table("oauth_consumers")
    op.drop_table("comments")
    op.drop_table("ratings")
    op.drop_index("rel_req_python_name_idx", table_name="release_requires_python")
    op.drop_index(
        "rel_req_python_name_version_idx", table_name="release_requires_python"
    )
    op.drop_index("rel_req_python_version_id_idx", table_name="release_requires_python")
    op.drop_table("release_requires_python")
    op.drop_index("release_urls_name_idx", table_name="release_urls")
    op.drop_index("release_urls_packagetype_idx", table_name="release_urls")
    op.drop_index("release_urls_version_idx", table_name="release_urls")
    op.drop_table("release_urls")
    op.drop_table("oid_associations")
    op.drop_table("openid_sessions")
    op.drop_table("openid_whitelist")
    op.drop_table("cheesecake_subindices")
    op.drop_index("sshkeys_name", table_name="sshkeys")
    op.drop_table("sshkeys")
    op.drop_index("openid_nonces_created", table_name="openid_nonces")
    op.drop_index("openid_nonces_nonce", table_name="openid_nonces")
    op.drop_table("openid_nonces")
    op.drop_constraint(
        "releases_cheesecake_installability_id_fkey", "releases", type_="foreignkey"
    )
    op.drop_constraint(
        "releases_cheesecake_code_kwalitee_id_fkey", "releases", type_="foreignkey"
    )
    op.drop_constraint(
        "releases_cheesecake_documentation_id_fkey", "releases", type_="foreignkey"
    )
    op.drop_column("releases", "cheesecake_documentation_id")
    op.drop_column("releases", "cheesecake_code_kwalitee_id")
    op.drop_column("releases", "cheesecake_installability_id")
    op.drop_table("cheesecake_main_indices")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
