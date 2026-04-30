import uuid
from datetime import datetime, timezone
from ..extensions import db

class AttackCoverageRun(db.Model):
    __tablename__ = "attack_coverage_run"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    tool_id = db.Column(db.String(36), db.ForeignKey("tool_inventory.id"), nullable=False)
    tool_fingerprint = db.Column(db.String(64), nullable=False)
    response_payload = db.Column(db.Text, nullable=False)   # JSON array
    model_used = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tool = db.relationship("ToolInventory")

    def __repr__(self):
        return f"<AttackCoverageRun tool={self.tool_id} fingerprint={self.tool_fingerprint[:8]}>"
