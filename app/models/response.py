import uuid
from datetime import datetime, timezone
from ..extensions import db


class Response(db.Model):
    __tablename__ = "response"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    pillar = db.Column(db.String(100), nullable=False)
    activity_id = db.Column(db.String(100), nullable=False)
    current_state_value = db.Column(db.String(50), nullable=True)
    target_state_value = db.Column(db.String(50), nullable=True)
    evidence_notes = db.Column(db.Text, nullable=True)
    last_edited_by = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    assessment = db.relationship("Assessment", back_populates="responses")
    editor = db.relationship("User", foreign_keys=[last_edited_by])

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "activity_id", name="uq_assessment_activity"),
    )

    def __repr__(self):
        return f"<Response {self.activity_id} {self.current_state_value}>"

    def has_gap(self, maturity_order: dict) -> bool:
        if not self.current_state_value or not self.target_state_value:
            return False
        return maturity_order.get(self.current_state_value, 0) < maturity_order.get(self.target_state_value, 0)
