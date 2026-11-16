"""Link a verified album review to its related catalog songs.

Revision ID: 7c49e8a0f21d
Revises: 55ea10177859
"""
from alembic import op
import sqlalchemy as sa

revision='7c49e8a0f21d'
down_revision='55ea10177859'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('review_link',
        sa.Column('song_id',sa.Integer(),sa.ForeignKey('song.id'),primary_key=True),
        sa.Column('review_id',sa.Integer(),sa.ForeignKey('review.id'),primary_key=True),
        sa.Column('kind',sa.String(16),nullable=False),
        sa.CheckConstraint("kind IN ('song','album','album_track')"))
    op.create_index('ix_review_link_review_id','review_link',['review_id'])
    op.execute("INSERT INTO review_link(song_id,review_id,kind) SELECT song_id,id,'song' FROM review")


def downgrade():
    op.drop_index('ix_review_link_review_id',table_name='review_link')
    op.drop_table('review_link')
