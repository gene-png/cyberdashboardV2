import uuid
from datetime import datetime, timezone
from ..extensions import db


class MappingSuggestionsLog(db.Model):
    __tablename__ = "mapping_suggestions_log"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_id = db.Column(db.String(36), db.ForeignKey("tool_inventory.id"), nullable=False)
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    request_payload = db.Column(db.Text, nullable=True)
    response_payload = db.Column(db.Text, nullable=True)
    model_used = db.Column(db.String(100), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    tool = db.relationship("ToolInventory", back_populates="suggestion_logs")

    def __repr__(self):
        return f"<MappingSuggestionsLog tool={self.tool_id} model={self.model_used}>"
