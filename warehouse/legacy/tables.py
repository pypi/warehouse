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

# Note: Tables that exist here should not be used anywhere, they only exist
#       here for migration support with alembic. If any of these tables end up
#       being used they should be moved outside of warehouse.legacy. The goal
#       is that once the legacy PyPI code base is gone, that these tables
#       can just be deleted and a migration made to drop them from the
#       database.

from citext import CIText
from sqlalchemy import (
    CheckConstraint, Column, ForeignKey, ForeignKeyConstraint, Index, Table,
    UniqueConstraint,
    Boolean, Date, DateTime, Integer, LargeBinary, String, Text,
)

from warehouse import db


accounts_gpgkey = Table(
    "accounts_gpgkey",
    db.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column(
        "user_id",
        Integer(),
        ForeignKey(
            "accounts_user.id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    ),
    Column("key_id", CIText(), nullable=False),
    Column("verified", Boolean(), nullable=False),

    UniqueConstraint("key_id", name="accounts_gpgkey_key_id_key"),

    CheckConstraint(
        "key_id ~* '^[A-F0-9]{8}$'::citext",
        name="accounts_gpgkey_valid_key_id",
    ),
)


Index("accounts_gpgkey_user_id", accounts_gpgkey.c.user_id)


browse_tally = Table(
    "browse_tally",
    db.metadata,

    Column("trove_id", Integer(), primary_key=True, nullable=False),
    Column("tally", Integer()),
)


cheesecake_main_indices = Table(
    "cheesecake_main_indices",
    db.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("absolute", Integer(), nullable=False),
    Column("relative", Integer(), nullable=False),
)


cheesecake_subindices = Table(
    "cheesecake_subindices",
    db.metadata,

    Column(
        "main_index_id",
        Integer(),
        ForeignKey("cheesecake_main_indices.id"),
        primary_key=True,
        nullable=False,
    ),
    Column("name", Text(), primary_key=True, nullable=False),
    Column("value", Integer(), nullable=False),
    Column("details", Text(), nullable=False),
)


comments = Table(
    "comments",
    db.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column(
        "rating",
        Integer(),
        ForeignKey("ratings.id", ondelete="CASCADE"),
    ),
    Column(
        "user_name",
        CIText(),
        ForeignKey("accounts_user.username", ondelete="CASCADE"),
    ),
    Column("date", DateTime(timezone=False)),
    Column("message", Text()),
    Column(
        "in_reply_to",
        Integer(),
        ForeignKey("comments.id", ondelete="CASCADE"),
    ),
)


comments_journal = Table(
    "comments_journal",
    db.metadata,

    Column("name", Text()),
    Column("version", Text()),
    Column("id", Integer()),
    Column(
        "submitted_by",
        CIText(),
        ForeignKey("accounts_user.username", ondelete="CASCADE"),
    ),
    Column("date", DateTime(timezone=False)),
    Column("action", Text()),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    ),
)


cookies = Table(
    "cookies",
    db.metadata,

    Column("cookie", Text(), primary_key=True, nullable=False),
    Column(
        "name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    ),
    Column("last_seen", DateTime(timezone=False)),
)


Index("cookies_last_seen", cookies.c.last_seen)


csrf_tokens = Table(
    "csrf_tokens",
    db.metadata,

    Column(
        "name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        primary_key=True,
        nullable=False,
    ),
    Column("token", Text()),
    Column("end_date", DateTime(timezone=False)),
)


description_urls = Table(
    "description_urls",
    db.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("name", Text()),
    Column("version", Text()),
    Column("url", Text()),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
    ),
)

Index("description_urls_name_idx", description_urls.c.name)


Index(
    "description_urls_name_version_idx",

    description_urls.c.name,
    description_urls.c.version,
)


dual = Table(
    "dual",
    db.metadata,

    Column("dummy", Integer()),
)


mirrors = Table(
    "mirrors",
    db.metadata,

    Column("ip", Text(), primary_key=True, nullable=False),
    Column("user_name", CIText(), ForeignKey("accounts_user.username")),
    Column("index_url", Text()),
    Column("last_modified_url", Text()),
    Column("local_stats_url", Text()),
    Column("stats_url", Text()),
    Column("mirrors_url", Text()),
)


oauth_access_tokens = Table(
    "oauth_access_tokens",
    db.metadata,

    Column("token", String(32), primary_key=True, nullable=False),
    Column("secret", String(64), nullable=False),
    Column("consumer", String(32), nullable=False),
    Column("date_created", Date(), nullable=False),
    Column("last_modified", Date(), nullable=False),
    Column(
        "user_name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    ),
)


oauth_consumers = Table(
    "oauth_consumers",
    db.metadata,

    Column("consumer", String(32), primary_key=True, nullable=False),
    Column("secret", String(64), nullable=False),
    Column("date_created", Date(), nullable=False),
    Column(
        "created_by",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
        ),
    ),
    Column("last_modified", Date(), nullable=False),
    Column("description", String(255), nullable=False),
)


oauth_nonce = Table(
    "oauth_nonce",
    db.metadata,

    Column("timestamp", Integer(), nullable=False),
    Column("consumer", String(32), nullable=False),
    Column("nonce", String(32), nullable=False),
    Column("token", String(32)),
)


oauth_request_tokens = Table(
    "oauth_request_tokens",
    db.metadata,

    Column("token", String(32), primary_key=True, nullable=False),
    Column("secret", String(64), nullable=False),
    Column("consumer", String(32), nullable=False),
    Column("callback", Text()),
    Column("date_created", Date(), nullable=False),
    Column(
        "user_name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    ),
)


oid_associations = Table(
    "oid_associations",
    db.metadata,

    Column("server_url", String(2047), primary_key=True, nullable=False),
    Column("handle", String(255), primary_key=True, nullable=False),
    Column("secret", LargeBinary(128), nullable=False),
    Column("issued", Integer(), nullable=False),
    Column("lifetime", Integer(), nullable=False),
    Column("assoc_type", String(64), nullable=False),

    CheckConstraint(
        "length(secret) <= 128",
        name="secret_length_constraint",
    ),
)


oid_nonces = Table(
    "oid_nonces",
    db.metadata,

    Column("server_url", String(2047), primary_key=True, nullable=False),
    Column("timestamp", Integer(), primary_key=True, nullable=False),
    Column("salt", String(40), primary_key=True, nullable=False),
)


openid_discovered = Table(
    "openid_discovered",
    db.metadata,

    Column("url", Text(), primary_key=True, nullable=False),
    Column("created", DateTime(timezone=False)),
    Column("services", LargeBinary()),
    Column("op_endpoint", Text()),
    Column("op_local", Text()),
)


openid_nonces = Table(
    "openid_nonces",
    db.metadata,

    Column("created", DateTime(timezone=False)),
    Column("nonce", Text()),
)


Index("openid_nonces_created", openid_nonces.c.created)


Index("openid_nonces_nonce", openid_nonces.c.nonce)


openid_sessions = Table(
    "openid_sessions",
    db.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("url", Text()),
    Column("assoc_handle", Text()),
    Column("expires", DateTime(timezone=False)),
    Column("mac_key", Text()),
)


openid_whitelist = Table(
    "openid_whitelist",
    db.metadata,

    Column("name", Text(), primary_key=True, nullable=False),
    Column("trust_root", Text(), primary_key=True, nullable=False),
    Column("created", DateTime(timezone=False)),
)


openids = Table(
    "openids",
    db.metadata,

    Column("id", Text(), primary_key=True, nullable=False),
    Column(
        "name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    ),
    Column("sub", Text()),
)


Index('openids_subkey', openids.c.sub, unique=True)


ratings = Table(
    "ratings",
    db.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column("name", Text(), nullable=False),
    Column("version", Text(), nullable=False),
    Column(
        "user_name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            ondelete="CASCADE",
        ),
        nullable=False
    ),
    Column("date", DateTime(timezone=False)),
    Column("rating", Integer()),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    ),

    UniqueConstraint("name", "version", "user_name", name="ratings_name_key"),
)


Index("rating_name_version", ratings.c.name, ratings.c.version)


rego_otk = Table(
    "rego_otk",
    db.metadata,

    Column(
        "name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            ondelete="CASCADE",
        ),
    ),
    Column("otk", Text()),
    Column("date", DateTime(timezone=False)),

    UniqueConstraint("otk", name="rego_otk_unique"),
)


Index("rego_otk_name_idx", rego_otk.c.name)


Index("rego_otk_otk_idx", rego_otk.c.otk)


release_requires_python = Table(
    "release_requires_python",
    db.metadata,

    Column("name", Text()),
    Column("version", Text()),
    Column("specifier", Text()),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
    ),
)


Index("rel_req_python_name_idx", release_requires_python.c.name)


Index(
    "rel_req_python_name_version_idx",
    release_requires_python.c.name,
    release_requires_python.c.version,
)


Index("rel_req_python_version_id_idx", release_requires_python.c.version)


release_urls = Table(
    "release_urls",
    db.metadata,

    Column("name", Text()),
    Column("version", Text()),
    Column("url", Text()),
    Column("packagetype", Text()),

    ForeignKeyConstraint(
        ["name", "version"],
        ["releases.name", "releases.version"],
        onupdate="CASCADE",
    ),
)


Index("release_urls_name_idx", release_urls.c.name)


Index("release_urls_packagetype_idx", release_urls.c.packagetype)


Index("release_urls_version_idx", release_urls.c.version)


sshkeys = Table(
    "sshkeys",
    db.metadata,

    Column("id", Integer(), primary_key=True, nullable=False),
    Column(
        "name",
        CIText(),
        ForeignKey(
            "accounts_user.username",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    ),
    Column("key", Text()),
)


Index("sshkeys_name", sshkeys.c.name)


timestamps = Table(
    "timestamps",
    db.metadata,

    Column("name", Text(), primary_key=True, nullable=False),
    Column("value", DateTime(timezone=False)),
)
