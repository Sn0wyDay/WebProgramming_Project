"""Recheck saved track-to-album review links under the current matching rule."""
from alembic import op
import sqlalchemy as sa


revision = 'f120_review_match_version'
down_revision = 'e201_correct_snowman_title'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('review_link', sa.Column('match_version', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('review_link') as batch:
        batch.drop_column('match_version')
