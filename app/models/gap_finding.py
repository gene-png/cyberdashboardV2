import uuid
from datetime import datetime, timezone
from ..extensions import db


class GapFinding(db.Model):
    __tablename__ = "gap_finding"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    pillar = db.Column(db.String(100), nullable=False)
    activity_id = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(20), nullable=True)  # low | medium | high | critical
    scrubbed_prompt = db.Column(db.Text, nullable=True)
    scrubbed_response = db.Column(db.Text, nullable=True)
    rehydrated_response = db.Column(db.Text, nullable=True)
    is_stale = db.Column(db.Boolean, default=False, nullable=False)
    generated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    generated_by = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=True)

    assessment = db.relationship("Assessment", back_populates="gap_findings")
    generator = db.relationship("User", foreign_keys=[generated_by])

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "activity_id", name="uq_gap_finding_activity"),
    )

    def __repr__(self):
        return f"<GapFinding {self.activity_id} severity={self.severity}>"
