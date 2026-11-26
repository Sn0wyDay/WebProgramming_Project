"""Correct the catalog title without replacing the recording or its passages."""
from alembic import op
import sqlalchemy as sa

revision = 'e201_correct_snowman_title'
down_revision = 'd190_integrate_home'
branch_labels = None
depends_on = None


def rename(old, new):
    song = sa.table('song', sa.column('provider'), sa.column('external_id'), sa.column('title'))
    op.execute(song.update().where(
        song.c.provider == 'musicbrainz',
        song.c.external_id == '5f705a3e-43a4-44ed-909a-c2155499ba84',
        song.c.title == old,
    ).values(title=new))


def upgrade():
    rename('눈사림', '눈사람')


def downgrade():
    rename('눈사람', '눈사림')
