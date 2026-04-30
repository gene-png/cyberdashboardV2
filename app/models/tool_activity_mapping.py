import uuid
from datetime import datetime, timezone
from ..extensions import db


class ToolActivityMapping(db.Model):
    __tablename__ = "tool_activity_mapping"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_id = db.Column(db.String(36), db.ForeignKey("tool_inventory.id"), nullable=False)
    activity_id = db.Column(db.String(100), nullable=False)
    # ai_suggested: LLM proposed this; admin_confirmed: admin kept AI suggestion;
    # admin_added: admin manually added (no AI suggestion)
    source = db.Column(db.String(20), nullable=False, default="ai_suggested")
    ai_confidence = db.Column(db.String(10), nullable=True)  # high | medium | low
    ai_rationale = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tool = db.relationship("ToolInventory", back_populates="activity_mappings")

    def __repr__(self):
        return f"<ToolActivityMapping {self.tool_id} → {self.activity_id}>"
