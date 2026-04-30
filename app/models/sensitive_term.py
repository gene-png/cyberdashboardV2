import uuid
from ..extensions import db


class SensitiveTerm(db.Model):
    __tablename__ = "sensitive_term"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = db.Column(db.String(36), db.ForeignKey("assessment.id"), nullable=False)
    term = db.Column(db.String(500), nullable=False)
    replacement_token = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(20), nullable=False, default="auto")  # auto | user_added
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    assessment = db.relationship("Assessment", back_populates="sensitive_terms")

    def __repr__(self):
        return f"<SensitiveTerm {self.replacement_token}>"
