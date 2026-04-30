import uuid
from datetime import datetime, timezone
from ..extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Assessment(db.Model):
    __tablename__ = "assessment"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_org = db.Column(db.String(255), nullable=False)
    framework = db.Column(db.String(50), nullable=False)  # dod_zt | cisa_zt
    variant = db.Column(db.String(50), nullable=True)     # with_org_profile | zt_only
    status = db.Column(
        db.String(30),
        nullable=False,
        default="draft",
    )  # draft | in_progress | awaiting_review | finalized | reopened
    current_step = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    finalized_at = db.Column(db.DateTime(timezone=True), nullable=True)

    users = db.relationship("User", back_populates="assessment", cascade="all, delete-orphan")
    tool_inventory = db.relationship("ToolInventory", back_populates="assessment", cascade="all, delete-orphan")
    responses = db.relationship("Response", back_populates="assessment", cascade="all, delete-orphan")
    admin_scores = db.relationship("AdminScore", back_populates="assessment", cascade="all, delete-orphan")
    gap_findings = db.relationship("GapFinding", back_populates="assessment", cascade="all, delete-orphan")
    sensitive_terms = db.relationship("SensitiveTerm", back_populates="assessment", cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog", back_populates="assessment", cascade="all, delete-orphan")
    ai_call_logs = db.relationship("AICallLog", back_populates="assessment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Assessment {self.id} {self.customer_org}>"

    @property
    def is_editable_by_customer(self):
        return self.status in ("draft", "in_progress")

    @property
    def is_finalized(self):
        return self.status == "finalized"
