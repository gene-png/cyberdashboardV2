import uuid
from datetime import datetime, timezone
from ..extensions import db


class MappingChange(db.Model):
    __tablename__ = "mapping_change"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_id = db.Column(db.String(36), db.ForeignKey("tool_inventory.id"), nullable=False)
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=True)
    changed_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    before_state = db.Column(db.Text, nullable=True)  # JSON list of activity_ids before
    after_state = db.Column(db.Text, nullable=True)   # JSON list of activity_ids after

    tool = db.relationship("ToolInventory", back_populates="mapping_changes")

    def __repr__(self):
        return f"<MappingChange tool={self.tool_id} at={self.changed_at}>"
