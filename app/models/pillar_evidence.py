import uuid
from datetime import datetime, timezone
from ..extensions import db

class PillarEvidence(db.Model):
    __tablename__ = "pillar_evidence"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    pillar_name = db.Column(db.String(100), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    extracted_text = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    assessment = db.relationship("Assessment", back_populates="pillar_evidence")
