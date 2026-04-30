import uuid
from datetime import datetime, timezone
from ..extensions import db


class AICallLog(db.Model):
    __tablename__ = "ai_call_log"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    gap_finding_id = db.Column(db.String(36), db.ForeignKey("gap_finding.id"), nullable=True)
    request_body_scrubbed = db.Column(db.Text, nullable=True)
    response_body_scrubbed = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(100), nullable=True)
    tokens_in = db.Column(db.Integer, nullable=True)
    tokens_out = db.Column(db.Integer, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    assessment = db.relationship("Assessment", back_populates="ai_call_logs")
    gap_finding = db.relationship("GapFinding", foreign_keys=[gap_finding_id])

    def __repr__(self):
        return f"<AICallLog {self.model} tokens_in={self.tokens_in}>"
