"""drop pilot partner tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('test_signups', 'project_reviews', 'tester_applications', 'volunteer_tags', 'volunteer_profiles')


def upgrade() -> None:
    for table in TABLES:  # children first; indexes and constraints go with the table
        op.drop_table(table)


def downgrade() -> None:
    op.create_table('volunteer_profiles',
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('classification', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('roles', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), server_default='[]', nullable=False),
    sa.Column('interests', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), server_default='[]', nullable=False),
    sa.Column('consented_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('volunteer_tags',
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('tag_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['volunteer_profiles.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'tag_id')
    )
    op.create_index(op.f('ix_volunteer_tags_tag_id'), 'volunteer_tags', ['tag_id'], unique=False)
    op.create_table('tester_applications',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('innovation_id', sa.String(length=120), nullable=False),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='tester_application_status', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('source', sa.Enum('tester', 'admin', name='tester_application_source', native_enum=False, create_constraint=True, length=16), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('decided_by', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['volunteer_profiles.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'innovation_id', name='uq_tester_applications_user_innovation')
    )
    op.create_index(op.f('ix_tester_applications_innovation_id'), 'tester_applications', ['innovation_id'], unique=False)
    op.create_index(op.f('ix_tester_applications_user_id'), 'tester_applications', ['user_id'], unique=False)
    op.create_table('project_reviews',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('project_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('rating', sa.SmallInteger(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('rating BETWEEN 1 AND 5', name='ck_project_reviews_rating_range'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'user_id', name='uq_project_reviews_project_id_user_id')
    )
    op.create_index(op.f('ix_project_reviews_user_id'), 'project_reviews', ['user_id'], unique=False)
    op.create_table('test_signups',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('project_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('location_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'user_id', name='uq_test_signups_project_id_user_id')
    )
    op.create_index(op.f('ix_test_signups_user_id'), 'test_signups', ['user_id'], unique=False)
