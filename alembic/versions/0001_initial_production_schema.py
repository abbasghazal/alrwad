
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, UniqueConstraint

from database import Base
import models  # noqa: F401


revision: str = "0001_initial_production_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk_name(table_name: str, constraint: ForeignKeyConstraint) -> str:
    local = "_".join(column.name for column in constraint.columns)
    remote = constraint.elements[0].column.table.name
    return constraint.name or f"fk_{table_name}_{local}_{remote}"


def _constraint_name(table_name: str, constraint: UniqueConstraint) -> str:
    columns = "_".join(column.name for column in constraint.columns)
    return constraint.name or f"uq_{table_name}_{columns}"


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    constraints = inspector.get_unique_constraints(table_name) + inspector.get_foreign_keys(table_name)
    return constraint_name in {constraint.get("name") for constraint in constraints}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return index_name in {index.get("name") for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = list(Base.metadata.tables.values())
    for table in tables:
        if _has_table(inspector, table.name):
            continue
        columns = [
            Column(
                column.name,
                column.type,
                primary_key=column.primary_key,
                nullable=column.nullable,
                autoincrement=column.autoincrement,
                server_default=column.server_default,
            )
            for column in table.columns
        ]
        op.create_table(table.name, *columns)

    inspector = sa.inspect(bind)
    for table in tables:
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                constraint_name = _constraint_name(table.name, constraint)
                if _has_constraint(inspector, table.name, constraint_name):
                    continue
                op.create_unique_constraint(
                    constraint_name,
                    table.name,
                    [column.name for column in constraint.columns],
                )
            if isinstance(constraint, CheckConstraint):
                if constraint.name and _has_constraint(inspector, table.name, constraint.name):
                    continue
                op.create_check_constraint(constraint.name, table.name, constraint.sqltext)
        for constraint in table.foreign_key_constraints:
            constraint_name = _fk_name(table.name, constraint)
            if _has_constraint(inspector, table.name, constraint_name):
                continue
            op.create_foreign_key(
                constraint_name,
                table.name,
                constraint.elements[0].column.table.name,
                [column.name for column in constraint.columns],
                [element.column.name for element in constraint.elements],
            )
        for index in table.indexes:
            if _has_index(inspector, table.name, index.name):
                continue
            op.create_index(index.name, table.name, [column.name for column in index.columns], unique=index.unique)


def downgrade() -> None:
    tables = list(Base.metadata.tables.values())
    for table in reversed(tables):
        for constraint in table.foreign_key_constraints:
            op.drop_constraint(_fk_name(table.name, constraint), table.name, type_="foreignkey")
    for table in reversed(tables):
        for index in table.indexes:
            op.drop_index(index.name, table_name=table.name)
        op.drop_table(table.name)
