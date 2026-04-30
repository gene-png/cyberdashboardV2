import uuid
from datetime import datetime, timezone
from ..extensions import db

class CoverageReport(db.Model):
    __tablename__ = "coverage_report"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    generated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    generated_by = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=True)
    tool_count = db.Column(db.Integer, nullable=False, default=0)
    technique_count = db.Column(db.Integer, nullable=False, default=0)
    covered_count = db.Column(db.Integer, nullable=False, default=0)
    file_path = db.Column(db.String(500), nullable=False)
    model_used = db.Column(db.String(100), nullable=False)

    assessment = db.relationship("Assessment")

    def __repr__(self):
        return f"<CoverageReport {self.id[:8]} {self.generated_at}>"
