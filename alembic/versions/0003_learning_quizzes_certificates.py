"""add learning content, quizzes, and certificates

Revision ID: 0003_learning_quizzes_certificates
Revises: 0002_grade_sections_groups
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_learning_content"
down_revision: Union[str, None] = "0002_grade_sections_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return index_name in {index.get("name") for index in inspector.get_indexes(table_name)}


def _has_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    constraints = inspector.get_unique_constraints(table_name) + inspector.get_foreign_keys(table_name)
    return constraint_name in {constraint.get("name") for constraint in constraints}


def _index(inspector, table_name: str, column_name: str) -> None:
    index_name = f"ix_{table_name}_{column_name}"
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, [column_name], unique=False)


def _soft_delete_columns() -> list:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "lessons"):
        op.create_table(
            "lessons",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("video_url", sa.String(), nullable=True),
            sa.Column("attachment_url", sa.String(), nullable=True),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("duration_minutes", sa.Integer(), nullable=True),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
            *_soft_delete_columns(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("subject_id", "order_index", name="uq_lesson_subject_order"),
        )
    inspector = sa.inspect(bind)
    if not _has_constraint(inspector, "lessons", "fk_lessons_subject_id_subjects"):
        op.create_foreign_key("fk_lessons_subject_id_subjects", "lessons", "subjects", ["subject_id"], ["id"])
    if not _has_constraint(inspector, "lessons", "fk_lessons_deleted_by_users"):
        op.create_foreign_key("fk_lessons_deleted_by_users", "lessons", "users", ["deleted_by"], ["id"])
    for column in ("id", "subject_id", "order_index", "is_published", "created_at", "updated_at", "is_deleted"):
        _index(inspector, "lessons", column)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "quizzes"):
        op.create_table(
            "quizzes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.Column("lesson_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("pass_score", sa.Float(), nullable=False, server_default="60"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
            *_soft_delete_columns(),
            sa.PrimaryKeyConstraint("id"),
        )
    inspector = sa.inspect(bind)
    if not _has_constraint(inspector, "quizzes", "fk_quizzes_subject_id_subjects"):
        op.create_foreign_key("fk_quizzes_subject_id_subjects", "quizzes", "subjects", ["subject_id"], ["id"])
    if not _has_constraint(inspector, "quizzes", "fk_quizzes_lesson_id_lessons"):
        op.create_foreign_key("fk_quizzes_lesson_id_lessons", "quizzes", "lessons", ["lesson_id"], ["id"])
    if not _has_constraint(inspector, "quizzes", "fk_quizzes_deleted_by_users"):
        op.create_foreign_key("fk_quizzes_deleted_by_users", "quizzes", "users", ["deleted_by"], ["id"])
    for column in ("id", "subject_id", "lesson_id", "is_published", "created_at", "updated_at", "is_deleted"):
        _index(inspector, "quizzes", column)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "quiz_questions"):
        op.create_table(
            "quiz_questions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("quiz_id", sa.Integer(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("options", sa.Text(), nullable=False),
            sa.Column("correct_answer", sa.String(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("points", sa.Float(), nullable=False, server_default="1"),
            *_soft_delete_columns(),
            sa.PrimaryKeyConstraint("id"),
        )
    inspector = sa.inspect(bind)
    if not _has_constraint(inspector, "quiz_questions", "fk_quiz_questions_quiz_id_quizzes"):
        op.create_foreign_key("fk_quiz_questions_quiz_id_quizzes", "quiz_questions", "quizzes", ["quiz_id"], ["id"])
    if not _has_constraint(inspector, "quiz_questions", "fk_quiz_questions_deleted_by_users"):
        op.create_foreign_key("fk_quiz_questions_deleted_by_users", "quiz_questions", "users", ["deleted_by"], ["id"])
    for column in ("id", "quiz_id", "created_at", "updated_at", "is_deleted"):
        _index(inspector, "quiz_questions", column)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "quiz_attempts"):
        op.create_table(
            "quiz_attempts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("quiz_id", sa.Integer(), nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("answers", sa.Text(), nullable=False),
            sa.Column("score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
            *_soft_delete_columns(),
            sa.PrimaryKeyConstraint("id"),
        )
    inspector = sa.inspect(bind)
    if not _has_constraint(inspector, "quiz_attempts", "fk_quiz_attempts_quiz_id_quizzes"):
        op.create_foreign_key("fk_quiz_attempts_quiz_id_quizzes", "quiz_attempts", "quizzes", ["quiz_id"], ["id"])
    if not _has_constraint(inspector, "quiz_attempts", "fk_quiz_attempts_student_id_users"):
        op.create_foreign_key("fk_quiz_attempts_student_id_users", "quiz_attempts", "users", ["student_id"], ["id"])
    if not _has_constraint(inspector, "quiz_attempts", "fk_quiz_attempts_deleted_by_users"):
        op.create_foreign_key("fk_quiz_attempts_deleted_by_users", "quiz_attempts", "users", ["deleted_by"], ["id"])
    for column in ("id", "quiz_id", "student_id", "passed", "created_at", "updated_at", "is_deleted"):
        _index(inspector, "quiz_attempts", column)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "certificates"):
        op.create_table(
            "certificates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.Column("verification_code", sa.String(), nullable=False),
            sa.Column("final_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            *_soft_delete_columns(),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("student_id", "subject_id", name="uq_certificate_student_subject"),
            sa.UniqueConstraint("verification_code"),
        )
    inspector = sa.inspect(bind)
    if not _has_constraint(inspector, "certificates", "fk_certificates_student_id_users"):
        op.create_foreign_key("fk_certificates_student_id_users", "certificates", "users", ["student_id"], ["id"])
    if not _has_constraint(inspector, "certificates", "fk_certificates_subject_id_subjects"):
        op.create_foreign_key("fk_certificates_subject_id_subjects", "certificates", "subjects", ["subject_id"], ["id"])
    if not _has_constraint(inspector, "certificates", "fk_certificates_deleted_by_users"):
        op.create_foreign_key("fk_certificates_deleted_by_users", "certificates", "users", ["deleted_by"], ["id"])
    for column in ("id", "student_id", "subject_id", "verification_code", "issued_at", "created_at", "updated_at", "is_deleted"):
        _index(inspector, "certificates", column)


def downgrade() -> None:
    for table_name in ("certificates", "quiz_attempts", "quiz_questions", "quizzes", "lessons"):
        op.drop_table(table_name)
