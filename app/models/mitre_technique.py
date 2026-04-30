import uuid
from ..extensions import db

class MitreTechnique(db.Model):
    __tablename__ = "mitre_technique"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    technique_id = db.Column(db.String(20), nullable=False)        # "T1078" (parent ID)
    sub_technique_id = db.Column(db.String(20), nullable=True)     # "T1078.001" (full sub-ID)
    name = db.Column(db.String(200), nullable=False)
    tactic = db.Column(db.String(200), nullable=True)              # comma-separated tactic names
    description = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(500), nullable=True)
    is_sub_technique = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def full_id(self):
        """Canonical identifier: T1078 for parent, T1078.001 for sub-technique."""
        return self.sub_technique_id or self.technique_id

    def __repr__(self):
        return f"<MitreTechnique {self.full_id} {self.name[:30]}>"
