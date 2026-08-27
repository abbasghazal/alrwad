"""add grade sections and section groups

Revision ID: 0002_grade_sections_groups
Revises: 0001_initial_production_schema
Create Date: 2026-06-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_grade_sections_groups"
down_revision: Union[str, None] = "0001_initial_production_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    checks = inspector.get_unique_constraints(table_name) + inspector.get_foreign_keys(table_name)
    return constraint_name in {constraint.get("name") for constraint in checks}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return index_name in {index.get("name") for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "grade_sections"):
        op.create_table(
            "grade_sections",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("grade_level", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("grade_level", "name", name="uq_grade_section_name"),
        )
        inspector = sa.inspect(bind)

    if not _has_constraint(inspector, "grade_sections", "fk_grade_sections_deleted_by_users"):
        op.create_foreign_key("fk_grade_sections_deleted_by_users", "grade_sections", "users", ["deleted_by"], ["id"])
    for column_name in ("id", "grade_level", "created_at", "updated_at", "is_deleted"):
        index_name = f"ix_grade_sections_{column_name}"
        if not _has_index(inspector, "grade_sections", index_name):
            op.create_index(index_name, "grade_sections", [column_name], unique=False)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "section_groups"):
        op.create_table(
            "section_groups",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("section_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("section_id", "name", name="uq_section_group_name"),
        )
        inspector = sa.inspect(bind)

    if not _has_constraint(inspector, "section_groups", "fk_section_groups_section_id_grade_sections"):
        op.create_foreign_key("fk_section_groups_section_id_grade_sections", "section_groups", "grade_sections", ["section_id"], ["id"])
    if not _has_constraint(inspector, "section_groups", "fk_section_groups_deleted_by_users"):
        op.create_foreign_key("fk_section_groups_deleted_by_users", "section_groups", "users", ["deleted_by"], ["id"])
    for column_name in ("id", "section_id", "created_at", "updated_at", "is_deleted"):
        index_name = f"ix_section_groups_{column_name}"
        if not _has_index(inspector, "section_groups", index_name):
            op.create_index(index_name, "section_groups", [column_name], unique=False)

    inspector = sa.inspect(bind)
    if not _has_column(inspector, "users", "section_id"):
        op.add_column("users", sa.Column("section_id", sa.Integer(), nullable=True))
    if not _has_column(inspector, "users", "group_id"):
        op.add_column("users", sa.Column("group_id", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "users", "ix_users_section_id"):
        op.create_index("ix_users_section_id", "users", ["section_id"], unique=False)
    if not _has_index(inspector, "users", "ix_users_group_id"):
        op.create_index("ix_users_group_id", "users", ["group_id"], unique=False)
    if not _has_constraint(inspector, "users", "fk_users_section_id_grade_sections"):
        op.create_foreign_key("fk_users_section_id_grade_sections", "users", "grade_sections", ["section_id"], ["id"])
    if not _has_constraint(inspector, "users", "fk_users_group_id_section_groups"):
        op.create_foreign_key("fk_users_group_id_section_groups", "users", "section_groups", ["group_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_constraint(inspector, "users", "fk_users_group_id_section_groups"):
        op.drop_constraint("fk_users_group_id_section_groups", "users", type_="foreignkey")
    if _has_constraint(inspector, "users", "fk_users_section_id_grade_sections"):
        op.drop_constraint("fk_users_section_id_grade_sections", "users", type_="foreignkey")
    if _has_index(inspector, "users", "ix_users_group_id"):
        op.drop_index("ix_users_group_id", table_name="users")
    if _has_index(inspector, "users", "ix_users_section_id"):
        op.drop_index("ix_users_section_id", table_name="users")
    if _has_column(inspector, "users", "group_id"):
        op.drop_column("users", "group_id")
    if _has_column(inspector, "users", "section_id"):
        op.drop_column("users", "section_id")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "section_groups"):
        op.drop_table("section_groups")
    if _has_table(inspector, "grade_sections"):
        op.drop_table("grade_sections")
