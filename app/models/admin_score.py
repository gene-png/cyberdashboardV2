import uuid
from ..extensions import db


class AdminScore(db.Model):
    __tablename__ = "admin_score"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    pillar = db.Column(db.String(100), nullable=False)
    current_score = db.Column(db.Float, nullable=True)
    target_score = db.Column(db.Float, nullable=True)
    gap_summary = db.Column(db.Text, nullable=True)
    consultant_recommendation = db.Column(db.Text, nullable=True)

    assessment = db.relationship("Assessment", back_populates="admin_scores")

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "pillar", name="uq_admin_score_pillar"),
    )

    def __repr__(self):
        return f"<AdminScore {self.pillar}>"
