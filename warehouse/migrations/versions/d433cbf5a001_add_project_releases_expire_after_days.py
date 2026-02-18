import sqlalchemy as sa

from alembic import op

revision = "d433cbf5a001"
down_revision = "a6045de6d1fe"


def upgrade():
    op.add_column(
        "projects",
        sa.Column(
            "releases_expire_after_days",
            sa.Integer(),
            nullable=True,
            comment="If set, releases for this project will be automatically deleted "
            "after this many days.",
        ),
    )


def downgrade():
    op.drop_column("projects", "releases_expire_after_days")
