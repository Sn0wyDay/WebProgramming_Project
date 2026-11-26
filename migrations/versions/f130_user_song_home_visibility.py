"""Allow each user to remove songs from the home list."""
from alembic import op
import sqlalchemy as sa


revision = 'f130_user_song_home_visibility'
down_revision = 'f120_review_match_version'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_song', sa.Column('home_hidden', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('user_song') as batch:
        batch.drop_column('home_hidden')
