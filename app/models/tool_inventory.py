import uuid
from datetime import datetime, timezone
from ..extensions import db


class ToolInventory(db.Model):
    __tablename__ = "tool_inventory"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    vendor = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Mapping workflow fields
    mapping_status = db.Column(
        db.String(20), nullable=False, default="pending_review", server_default="pending_review"
    )  # pending_review | active
    mappings_finalized_at = db.Column(db.DateTime(timezone=True), nullable=True)
    mappings_finalized_by = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=True)

    assessment = db.relationship("Assessment", back_populates="tool_inventory")
    activity_mappings = db.relationship(
        "ToolActivityMapping", back_populates="tool", cascade="all, delete-orphan"
    )
    suggestion_logs = db.relationship(
        "MappingSuggestionsLog", back_populates="tool", cascade="all, delete-orphan"
    )
    mapping_changes = db.relationship(
        "MappingChange", back_populates="tool", cascade="all, delete-orphan"
    )

    @property
    def active_mappings(self) -> list:
        return [m for m in self.activity_mappings if self.mapping_status == "active"]

    def __repr__(self):
        return f"<ToolInventory {self.name}>"
