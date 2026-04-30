import uuid
from datetime import datetime, timezone
from ..extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)  # create|update|delete|submit|finalize|reopen|regenerate_finding
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.String(36), nullable=True)
    before_value = db.Column(db.Text, nullable=True)
    after_value = db.Column(db.Text, nullable=True)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    assessment = db.relationship("Assessment", back_populates="audit_logs")
    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<AuditLog {self.action} {self.target_type}>"
