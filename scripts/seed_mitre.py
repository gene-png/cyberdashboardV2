#!/usr/bin/env python3
"""
Seed the mitre_technique table from the MITRE ATT&CK Enterprise STIX dataset.

Usage:
    python scripts/seed_mitre.py                  # download from MITRE CTI GitHub
    python scripts/seed_mitre.py --file path.json # load from local file
    python scripts/seed_mitre.py --dry-run        # show counts, don't write

Idempotent: existing techniques (matched by full_id) are updated, not duplicated.
"""
import argparse
import json
import os
import sys
import urllib.request

# Bootstrap Flask app context
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

STIX_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"

TACTIC_DISPLAY = {
    "reconnaissance": "Reconnaissance",
    "resource-development": "Resource Development",
    "initial-access": "Initial Access",
    "execution": "Execution",
    "persistence": "Persistence",
    "privilege-escalation": "Privilege Escalation",
    "defense-evasion": "Defense Evasion",
    "credential-access": "Credential Access",
    "discovery": "Discovery",
    "lateral-movement": "Lateral Movement",
    "collection": "Collection",
    "command-and-control": "Command and Control",
    "exfiltration": "Exfiltration",
    "impact": "Impact",
}


def _fetch_stix(url: str) -> dict:
    print(f"Downloading STIX bundle from {url} ...")
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read())


def _parse_techniques(bundle: dict) -> list[dict]:
    """Extract technique records from a STIX bundle."""
    records = []
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        if obj.get("x_mitre_deprecated") or obj.get("x_mitre_revoked"):
            continue

        # Extract technique ID and URL
        ext_id = None
        url = None
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                ext_id = ref.get("external_id")
                url = ref.get("url")
                break
        if not ext_id:
            continue

        is_sub = obj.get("x_mitre_is_subtechnique", False)

        # Extract tactics (kill chain phases)
        tactics = []
        for phase in obj.get("kill_chain_phases", []):
            if phase.get("kill_chain_name") == "mitre-attack":
                display = TACTIC_DISPLAY.get(phase["phase_name"], phase["phase_name"])
                tactics.append(display)
        tactic_str = ", ".join(tactics) if tactics else None

        # Determine technique_id vs sub_technique_id
        if is_sub:
            parent_id = ext_id.split(".")[0]  # "T1078" from "T1078.001"
            technique_id = parent_id
            sub_technique_id = ext_id
        else:
            technique_id = ext_id
            sub_technique_id = None

        # Truncate description
        desc = obj.get("description", "") or ""
        if len(desc) > 2000:
            desc = desc[:1997] + "..."

        records.append({
            "technique_id": technique_id,
            "sub_technique_id": sub_technique_id,
            "name": obj["name"][:200],
            "tactic": tactic_str,
            "description": desc or None,
            "url": url,
            "is_sub_technique": is_sub,
        })

    return records


def seed(records: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """Upsert technique records. Returns (inserted, updated)."""
    from app import create_app
    from app.models.mitre_technique import MitreTechnique
    from app.extensions import db

    app = create_app()
    inserted = updated = 0

    with app.app_context():
        db.create_all()
        for rec in records:
            full_id = rec["sub_technique_id"] or rec["technique_id"]
            existing = MitreTechnique.query.filter(
                MitreTechnique.sub_technique_id == rec["sub_technique_id"]
                if rec["sub_technique_id"]
                else MitreTechnique.technique_id == rec["technique_id"],
                MitreTechnique.is_sub_technique == rec["is_sub_technique"],
            ).first()

            if existing:
                if not dry_run:
                    existing.name = rec["name"]
                    existing.tactic = rec["tactic"]
                    existing.description = rec["description"]
                    existing.url = rec["url"]
                updated += 1
            else:
                if not dry_run:
                    t = MitreTechnique(**rec)
                    db.session.add(t)
                inserted += 1

        if not dry_run:
            db.session.commit()

    return inserted, updated


def main():
    parser = argparse.ArgumentParser(description="Seed MITRE ATT&CK Enterprise techniques")
    parser.add_argument("--file", help="Path to local STIX JSON file")
    parser.add_argument("--url", default=STIX_URL, help="STIX bundle URL")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing")
    args = parser.parse_args()

    if args.file:
        print(f"Loading from {args.file} ...")
        with open(args.file) as f:
            bundle = json.load(f)
    else:
        bundle = _fetch_stix(args.url)

    records = _parse_techniques(bundle)
    print(f"Parsed {len(records)} techniques ({sum(1 for r in records if r['is_sub_technique'])} sub-techniques)")

    if args.dry_run:
        print("Dry run — not writing to DB.")
        return

    inserted, updated = seed(records)
    print(f"Done: {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    main()
