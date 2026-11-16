"""Distinguish reviews from editorial selection articles.

Revision ID: a91f378c20e4
Revises: 7c49e8a0f21d
"""
from alembic import op
import sqlalchemy as sa

revision='a91f378c20e4'
down_revision='7c49e8a0f21d'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('review') as batch:
        batch.add_column(sa.Column('article_type',sa.String(16),nullable=False,server_default='review'))
        batch.create_check_constraint('ck_review_article_type',"article_type IN ('review','selection')")
    with op.batch_alter_table('review_link') as batch:
        batch.add_column(sa.Column('context',sa.String(500),nullable=True))


def downgrade():
    with op.batch_alter_table('review_link') as batch:
        batch.drop_column('context')
    with op.batch_alter_table('review') as batch:
        batch.drop_constraint('ck_review_article_type',type_='check')
        batch.drop_column('article_type')
