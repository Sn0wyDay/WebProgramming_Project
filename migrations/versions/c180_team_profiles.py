"""Public team showcase track, separate from private user records."""
from alembic import op
import sqlalchemy as sa
revision = 'c180_team_profiles'
down_revision = 'a7afae7ee53f'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('team_profile', sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), primary_key=True), sa.Column('song_id', sa.Integer(), sa.ForeignKey('song.id'), nullable=False))

def downgrade():
    op.drop_table('team_profile')
