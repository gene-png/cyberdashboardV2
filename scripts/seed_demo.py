"""
Seed a realistic demo assessment using the CISA Zero Trust Maturity Model.

Usage:
    python scripts/seed_demo.py

Creates:
    - Customer user: acme_demo / DemoPass2024!
    - Assessment for "Acme Federal Solutions" (CISA ZT framework)
    - 6 security tools with mappings
    - Responses for all 14 activities with realistic maturity gaps
    - Evidence notes and consultant annotations
    - Representative gap findings

Safe to re-run: skips creation if the demo user already exists.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import (
    Assessment, User, Response, ToolInventory,
    ToolActivityMapping, GapFinding, AdminScore,
)
from datetime import datetime, timezone

DEMO_USERNAME = "acme_demo"
DEMO_PASSWORD = "DemoPass2024!"
DEMO_ORG = "Acme Federal Solutions"
DEMO_FRAMEWORK = "cisa_zt"

# ── Tool definitions ──────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "Entra ID",
        "vendor": "Microsoft",
        "category": "Identity & Access Management",
        "notes": "Deployed org-wide; MFA enforced for ~85% of users via Conditional Access. Privileged Identity Management (PIM) licensed but not fully configured.",
    },
    {
        "name": "Defender for Endpoint",
        "vendor": "Microsoft",
        "category": "Endpoint Protection",
        "notes": "P2 license. Deployed on all Windows endpoints and ~60% of macOS. Threat & Vulnerability Management enabled. Attack Surface Reduction rules in audit mode only.",
    },
    {
        "name": "Prisma Access",
        "vendor": "Palo Alto Networks",
        "category": "Zero Trust Network Access",
        "notes": "ZTNA deployed for remote workforce. On-prem traffic still routes through legacy VPN. App-ID policies partially configured.",
    },
    {
        "name": "Splunk Enterprise Security",
        "vendor": "Splunk",
        "category": "Security Information & Event Management",
        "notes": "SIEM with 90-day retention. Ingesting endpoint, network, and identity logs. UEBA add-on installed but risk scores not tuned. 24/7 SOC monitors critical alerts.",
    },
    {
        "name": "Tenable Vulnerability Management",
        "vendor": "Tenable",
        "category": "Vulnerability Management",
        "notes": "Weekly authenticated scans across all subnets. Critical/High findings tracked in Jira. Average remediation SLA: 30 days for criticals.",
    },
    {
        "name": "Purview Information Protection",
        "vendor": "Microsoft",
        "category": "Data Loss Prevention",
        "notes": "Sensitivity labels deployed for Office 365. DLP policies cover Exchange and SharePoint. Endpoint DLP not yet deployed. Rights Management enabled for classified documents.",
    },
]

# ── Activity responses: (activity_id, current, target, evidence_notes) ────────
RESPONSES = [
    # Identity pillar
    (
        "cisa_zt.identity.1.1", "initial", "advanced",
        "Active Directory federated with Entra ID. User lifecycle managed through HR-driven provisioning in Workday → Entra. Orphaned accounts reviewed quarterly; last audit found 12 stale accounts remediated. Role-based access reviews occur annually — not yet automated.",
    ),
    (
        "cisa_zt.identity.1.2", "advanced", "optimal",
        "MFA enforced via Entra Conditional Access for all cloud apps. FIDO2 security keys deployed for 200 privileged users. Remaining ~1,400 users use Microsoft Authenticator (TOTP). SMS fallback disabled. Phishing-resistant MFA not yet mandated for all users.",
    ),
    (
        "cisa_zt.identity.1.3", "initial", "advanced",
        "Entra ID Protection enabled with risk-based Conditional Access policies. Sign-in risk policy set to block high-risk logins. User risk policy triggers password reset at high risk. Risk score tuning in progress — current false positive rate ~8%.",
    ),
    (
        "cisa_zt.identity.1.4", "traditional", "advanced",
        "CyberArk PAM was decommissioned in 2023 due to cost. Currently using Entra PIM for Azure roles only. On-prem privileged accounts managed via shared service account with manual check-out log. No session recording for privileged access. JIT access not implemented.",
    ),
    # Devices pillar
    (
        "cisa_zt.devices.2.1", "initial", "advanced",
        "Intune MDM deployed for corporate Windows and iOS/Android. Asset inventory in ServiceNow CMDB synced from Intune daily. ~340 unmanaged contractor endpoints identified but not enrolled. Shadow IT devices detected on network — no formal remediation process.",
    ),
    (
        "cisa_zt.devices.2.2", "initial", "advanced",
        "Compliance policies configured in Intune: OS patch level, encryption, screen lock required. Non-compliant devices blocked from email via Conditional Access. 12% of devices currently out of compliance — mostly macOS endpoints missing OS updates. No real-time compliance enforcement for on-prem resources.",
    ),
    (
        "cisa_zt.devices.2.3", "advanced", "optimal",
        "Microsoft Defender for Endpoint P2 deployed on all managed Windows devices. EDR alerts feed into Splunk ES via API. Threat hunting conducted weekly by SOC. macOS coverage at 60% — migration to full Defender for Endpoint macOS in progress. No mobile threat defense (MTD) for iOS/Android.",
    ),
    # Networks pillar
    (
        "cisa_zt.networks.3.1", "initial", "advanced",
        "Campus network segmented into 8 VLANs by function (users, servers, IoT, guest, etc.). East-west traffic between VLANs not inspected — flat routing inside segments. Micro-segmentation not implemented. Data center uses legacy firewall rules with broad allow policies between server subnets.",
    ),
    (
        "cisa_zt.networks.3.2", "advanced", "optimal",
        "TLS 1.2+ enforced for all external web traffic. Internal service-to-service traffic uses TLS where supported — legacy applications use unencrypted internal APIs. VPN traffic encrypted via IPsec. DNS queries not encrypted (DoH/DoT not deployed). Certificate management partially automated via DigiCert.",
    ),
    (
        "cisa_zt.networks.3.3", "traditional", "advanced",
        "Remote access via legacy Cisco AnyConnect VPN for majority of workforce. Palo Alto Prisma Access deployed for 450 remote workers (30% of workforce). Full cutover planned for Q3. No identity-aware NAC for on-prem network access — MAC-based filtering only. Guest network isolated but no captive portal authentication.",
    ),
    # Applications pillar
    (
        "cisa_zt.applications.4.1", "initial", "advanced",
        "SSO via Entra ID for 78 of 120 enterprise applications. Remaining 42 apps use local accounts — migration roadmap in progress. App inventory maintained in ServiceNow. API gateway deployed for internal microservices. No formal application entitlement review process.",
    ),
    (
        "cisa_zt.applications.4.2", "traditional", "advanced",
        "SAST scanning integrated in CI/CD pipeline for 3 of 8 development teams. DAST scans run quarterly on production apps. No SCA (software composition analysis) tooling — open source dependency vulnerabilities tracked manually. Penetration testing conducted annually by third party. Bug bounty program not established.",
    ),
    (
        "cisa_zt.applications.4.3", "initial", "advanced",
        "Defender for Cloud deployed for Azure workloads — 94% of subscriptions covered. Container security scanning via Defender for Containers. On-prem workloads not covered by cloud CNAPP. Runtime protection for containers not enabled. Serverless functions not inventoried for security.",
    ),
    # Data pillar
    (
        "cisa_zt.data.5.1", "initial", "advanced",
        "Microsoft Purview sensitivity labels applied to Office 365 (Public, Internal, Confidential, Highly Confidential). Auto-classification rules deployed for SSNs, credit card numbers, and contract data. ~30% of SharePoint content auto-labeled. Structured data in SQL databases not classified. Data discovery for on-prem file shares pending.",
    ),
    (
        "cisa_zt.data.5.2", "initial", "advanced",
        "RBAC enforced for SharePoint and Teams via Entra groups. Sensitive SharePoint sites require Conditional Access compliant device. External sharing restricted to approved domains. Database access managed through service accounts — no row-level security. Privileged data access not logged in SIEM.",
    ),
    (
        "cisa_zt.data.5.3", "advanced", "optimal",
        "BitLocker enforced on all Windows endpoints via Intune. Azure Storage and SQL databases use platform-managed encryption at rest. Customer-managed keys (CMK) not implemented — using Microsoft-managed keys. Backup encryption enabled. Encryption key rotation automated annually.",
    ),
    (
        "cisa_zt.data.5.4", "traditional", "advanced",
        "Purview DLP policies cover Exchange Online (block external send of SSNs/PCI data) and SharePoint (restrict download of Confidential+ files). Endpoint DLP not deployed — USB and print exfiltration not blocked. Cloud app DLP via Defender for Cloud Apps in monitor-only mode. No DLP coverage for on-prem file servers.",
    ),
]

# ── Tool → activity mappings (tool index, [activity_ids]) ────────────────────
TOOL_MAPPINGS = {
    0: [  # Entra ID
        "cisa_zt.identity.1.1",
        "cisa_zt.identity.1.2",
        "cisa_zt.identity.1.3",
        "cisa_zt.identity.1.4",
        "cisa_zt.networks.3.3",
        "cisa_zt.applications.4.1",
    ],
    1: [  # Defender for Endpoint
        "cisa_zt.devices.2.1",
        "cisa_zt.devices.2.2",
        "cisa_zt.devices.2.3",
        "cisa_zt.applications.4.3",
    ],
    2: [  # Prisma Access
        "cisa_zt.networks.3.1",
        "cisa_zt.networks.3.2",
        "cisa_zt.networks.3.3",
    ],
    3: [  # Splunk ES
        "cisa_zt.identity.1.3",
        "cisa_zt.devices.2.3",
        "cisa_zt.networks.3.1",
        "cisa_zt.applications.4.2",
    ],
    4: [  # Tenable
        "cisa_zt.devices.2.2",
        "cisa_zt.devices.2.3",
        "cisa_zt.applications.4.2",
        "cisa_zt.applications.4.3",
    ],
    5: [  # Purview
        "cisa_zt.data.5.1",
        "cisa_zt.data.5.2",
        "cisa_zt.data.5.3",
        "cisa_zt.data.5.4",
    ],
}

# ── Consultant annotations per pillar ────────────────────────────────────────
PILLAR_NOTES = {
    "identity": {
        "gap_summary": (
            "Identity is the strongest pillar but PAM is a critical gap. "
            "Entra ID provides a solid foundation; the priority is implementing JIT privileged access "
            "and extending phishing-resistant MFA to all users before end of fiscal year."
        ),
        "consultant_recommendation": (
            "1. Enable Entra PIM for all privileged on-prem roles via Azure AD Connect sync. "
            "2. Mandate FIDO2 for all users with access to sensitive systems by Q2. "
            "3. Automate quarterly access certification in Entra ID Governance. "
            "Estimated effort: High — requires change management and user training."
        ),
    },
    "devices": {
        "gap_summary": (
            "Device management is partially mature. The primary gap is unmanaged contractor devices "
            "and incomplete macOS EDR coverage. Compliance enforcement is reactive rather than continuous."
        ),
        "consultant_recommendation": (
            "1. Require Intune enrollment for contractor devices within 90 days via a device-based Conditional Access policy. "
            "2. Complete Defender for Endpoint macOS deployment — target 100% by Q2. "
            "3. Enable real-time compliance enforcement for on-prem resources via NPS extension. "
            "4. Implement Mobile Threat Defense for iOS/Android via Defender for Mobile."
        ),
    },
    "networks": {
        "gap_summary": (
            "Network segmentation exists at macro level but lacks inspection between segments. "
            "Legacy VPN dependency is the largest barrier — full Prisma Access rollout is the critical path."
        ),
        "consultant_recommendation": (
            "1. Accelerate Prisma Access rollout — complete the remaining 70% of workforce by Q3. "
            "2. Deploy Palo Alto Panorama to enforce east-west traffic inspection between VLANs. "
            "3. Implement DoH/DoT for DNS encryption using Entra Private DNS Resolver. "
            "4. Retire Cisco AnyConnect once Prisma Access reaches 100% coverage."
        ),
    },
    "applications": {
        "gap_summary": (
            "Application security testing is the weakest sub-pillar — most development teams lack SAST/SCA tooling. "
            "Cloud workload protection is strong for Azure but on-prem remains a blind spot."
        ),
        "consultant_recommendation": (
            "1. Mandate GitHub Advanced Security (SAST + SCA) across all 8 development teams by Q2. "
            "2. Integrate Defender for Cloud with on-prem servers via Azure Arc. "
            "3. Enable container runtime protection in Defender for Containers. "
            "4. Establish quarterly application entitlement reviews using Entra ID Governance."
        ),
    },
    "data": {
        "gap_summary": (
            "Data protection has a strong cloud-first foundation but on-prem and endpoint coverage are the critical gaps. "
            "DLP is monitor-only for cloud apps and entirely absent for endpoints and file servers."
        ),
        "consultant_recommendation": (
            "1. Deploy Purview Endpoint DLP to block USB exfiltration and unmanaged print for Confidential+ data. "
            "2. Switch Defender for Cloud Apps DLP from monitor-only to enforcement mode. "
            "3. Extend auto-classification to SQL databases using Purview Data Map. "
            "4. Implement customer-managed keys (CMK) in Azure Key Vault for regulated data stores."
        ),
    },
}

# ── Gap findings (placeholder — realistic AI-style output) ───────────────────
FINDINGS = [
    {
        "activity_id": "cisa_zt.identity.1.4",
        "pillar": "identity",
        "severity": "critical",
        "text": (
            "**Gap summary**\n"
            "Privileged Access Management is at Traditional maturity with no JIT access, no session recording, "
            "and privileged on-prem accounts managed via shared credentials — creating significant lateral movement risk "
            "that must be resolved to reach Advanced maturity.\n\n"
            "**Steps to reach Advanced**\n"
            "1. Enable Entra Privileged Identity Management (PIM) for all Azure AD roles immediately — "
            "configure eligible assignments with 4-hour maximum activation windows and MFA on activation.\n"
            "2. Sync on-prem AD privileged groups to Entra ID via Azure AD Connect and bring them under PIM governance — "
            "target: Domain Admins, Enterprise Admins, Schema Admins, and all Tier-0 service accounts.\n"
            "3. Deploy Entra ID session policies to enforce re-authentication every 8 hours for privileged sessions "
            "and enable Privileged Access Workstations (PAWs) for Tier-0 administration.\n"
            "4. Enable Microsoft Defender for Identity (MDI) to detect credential theft, lateral movement, "
            "and privilege escalation in the on-prem environment.\n"
            "5. Establish a weekly PIM access review process using Entra ID Governance access reviews — "
            "automatically revoke assignments not approved within 7 days.\n\n"
            "**Leverage existing tools**\n"
            "Microsoft Entra ID (PIM): Enable eligible role assignments for all Azure and synced on-prem privileged roles. "
            "Set activation policy to require MFA + justification. "
            "Splunk Enterprise Security: Create a detection for PIM activation outside business hours and for "
            "any direct role assignment bypassing PIM (alert on AuditLogs where activity = 'Add member to role' and initiatedBy != 'PIM').\n\n"
            "**Effort estimate**: High — PAM program requires executive sponsorship, change management for admin workflows, "
            "and 60–90 days to complete discovery and migration of all privileged accounts."
        ),
    },
    {
        "activity_id": "cisa_zt.networks.3.3",
        "pillar": "networks",
        "severity": "high",
        "text": (
            "**Gap summary**\n"
            "Network access control remains at Traditional maturity for 70% of the workforce still using legacy VPN, "
            "with no identity-aware NAC for on-premises access — allowing any device on the network segment "
            "to reach resources regardless of identity or compliance state.\n\n"
            "**Steps to reach Advanced**\n"
            "1. Accelerate the Palo Alto Prisma Access rollout from 30% to 100% of workforce — "
            "prioritize all users accessing sensitive data (Finance, Legal, Engineering) in the next 30 days.\n"
            "2. Configure Prisma Access App-ID and User-ID policies to enforce least-privilege application access "
            "based on Entra group membership — replace broad subnet-to-subnet firewall rules with named application policies.\n"
            "3. Deploy 802.1X with EAP-TLS certificate authentication for on-prem wired and wireless access, "
            "integrated with Entra ID via NPS extension — block non-compliant and unregistered devices at the network layer.\n"
            "4. Implement a captive portal with Entra ID authentication for the guest network and contractor segments.\n\n"
            "**Leverage existing tools**\n"
            "Palo Alto Prisma Access: Configure the GlobalProtect gateway with pre-logon authentication and enforce "
            "HIP (Host Information Profile) checks to block devices not compliant with Intune policies. "
            "Microsoft Entra ID: Use the Entra ID Network Access (Global Secure Access) preview for on-premises "
            "resource access policies — this provides identity-aware NAC without requiring additional hardware.\n\n"
            "**Effort estimate**: High — full VPN migration affects all employees and requires parallel-running "
            "both systems during transition; allow 90 days minimum with phased user group rollout."
        ),
    },
    {
        "activity_id": "cisa_zt.data.5.4",
        "pillar": "data",
        "severity": "high",
        "text": (
            "**Gap summary**\n"
            "Data Loss Prevention is at Traditional maturity with no endpoint DLP and only monitor-only cloud app policies, "
            "leaving USB exfiltration, unmanaged print, and cloud app data movement entirely uncontrolled "
            "for Confidential and above data.\n\n"
            "**Steps to reach Advanced**\n"
            "1. Deploy Microsoft Purview Endpoint DLP to all Intune-managed Windows endpoints — "
            "configure policies to block copy of Confidential+ sensitivity-labeled files to USB, "
            "unmanaged cloud locations, and personal email within 30 days.\n"
            "2. Switch Defender for Cloud Apps DLP policies from monitor-only to block mode for "
            "sanctioned apps (SharePoint, Teams, OneDrive) — start with Confidential label, "
            "expand to Internal after 2-week validation period.\n"
            "3. Enable Purview Communication Compliance to scan outbound email for untagged sensitive data "
            "patterns (SSNs, contract numbers, ITAR-controlled terms) — route matches to compliance reviewers.\n"
            "4. Extend DLP coverage to on-prem file servers via Purview on-premises scanner — "
            "inventory and label all shares containing Confidential data.\n\n"
            "**Leverage existing tools**\n"
            "Microsoft Purview Information Protection: Use existing sensitivity labels as the DLP policy "
            "condition — no re-classification needed. Enable 'Endpoint DLP' in the Microsoft Purview compliance portal "
            "and target the existing Intune device group. "
            "Splunk Enterprise Security: Ingest Purview DLP alerts via the Microsoft 365 Defender connector "
            "and create a Notable Event for any block action or repeated policy violation by a single user.\n\n"
            "**Effort estimate**: Medium — Purview Endpoint DLP is licensed (M365 E5) and deploys via existing Intune; "
            "the main effort is policy tuning to avoid false positives before switching cloud app policies to block mode."
        ),
    },
    {
        "activity_id": "cisa_zt.applications.4.2",
        "pillar": "applications",
        "severity": "high",
        "text": (
            "**Gap summary**\n"
            "Application security testing is Traditional for 5 of 8 development teams with no SAST or SCA tooling, "
            "meaning open-source vulnerabilities and insecure code patterns are not detected until post-deployment "
            "or annual pen tests — creating exploitable windows measured in months.\n\n"
            "**Steps to reach Advanced**\n"
            "1. Enable GitHub Advanced Security on all repositories within 30 days — "
            "activate CodeQL SAST and Secret Scanning with push protection to block credential commits.\n"
            "2. Enable Dependabot for all repos to auto-generate PRs for vulnerable dependency updates — "
            "configure auto-merge for patch-level updates with passing tests.\n"
            "3. Add OWASP ZAP or Burp Suite Enterprise to the CI/CD pipeline for DAST scanning on staging "
            "environments — block deployment on critical findings.\n"
            "4. Integrate Tenable Web App Scanning for quarterly production DAST and feed results into the "
            "existing Jira vulnerability tracking workflow.\n\n"
            "**Leverage existing tools**\n"
            "Tenable Vulnerability Management: Tenable includes Web Application Scanning (WAS) — enable it for "
            "the 42 external-facing apps and schedule weekly scans. Map findings to the existing Jira workflow "
            "used for infrastructure vulnerabilities. "
            "Splunk Enterprise Security: Create a dashboard tracking open AppSec findings by team and age — "
            "use the Tenable add-on for Splunk to ingest WAS scan results alongside infrastructure vulnerability data.\n\n"
            "**Effort estimate**: Medium — GitHub Advanced Security is available if org uses GitHub Enterprise; "
            "enablement is low-effort but tuning CodeQL queries and establishing PR review gates requires "
            "4–6 weeks of developer education and policy enforcement."
        ),
    },
    {
        "activity_id": "cisa_zt.identity.1.1",
        "pillar": "identity",
        "severity": "medium",
        "text": (
            "**Gap summary**\n"
            "Identity governance is at Initial maturity with annual access reviews and no automated provisioning "
            "de-provisioning enforcement, meaning access accumulates over time and orphaned accounts create "
            "unnecessary attack surface.\n\n"
            "**Steps to reach Advanced**\n"
            "1. Enable Entra ID Governance Access Reviews for all application roles and groups — "
            "schedule quarterly reviews for privileged access, semi-annual for standard access.\n"
            "2. Configure automated access removal: set reviews to auto-remove access for non-responders "
            "after 14 days, and auto-apply results upon review completion.\n"
            "3. Build a Lifecycle Workflow in Entra ID Governance to auto-disable accounts within 1 business day "
            "of HR termination event in Workday — remove all application assignments and revoke sessions.\n"
            "4. Enable Entra ID Governance Entitlement Management to replace manual role requests with "
            "self-service access packages including approval workflows and expiration dates.\n\n"
            "**Leverage existing tools**\n"
            "Microsoft Entra ID (Governance): All required capabilities (Access Reviews, Lifecycle Workflows, "
            "Entitlement Management) are included in the Entra ID Governance license already deployed. "
            "Configure the Workday → Entra provisioning connector to pass termination date as a trigger attribute "
            "for the Lifecycle Workflow. "
            "Splunk Enterprise Security: Alert on accounts active more than 7 days post-HR termination date "
            "by correlating Workday HR feed (via REST API) with Entra ID sign-in logs.\n\n"
            "**Effort estimate**: Medium — Entra Governance configuration is straightforward; the primary effort "
            "is stakeholder alignment on access review ownership and a 4–6 week change management campaign."
        ),
    },
]


def seed():
    app = create_app()
    with app.app_context():
        # Idempotency check
        if User.query.filter_by(username=DEMO_USERNAME).first():
            print(f"Demo user '{DEMO_USERNAME}' already exists — skipping.")
            print(f"\nLogin at /resume with:\n  Name/username: {DEMO_USERNAME}\n  Password: {DEMO_PASSWORD}")
            return

        print(f"Creating demo assessment for '{DEMO_ORG}'...")

        # Assessment
        assessment = Assessment(
            customer_org=DEMO_ORG,
            framework=DEMO_FRAMEWORK,
            variant="zt_only",
            status="draft",
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(assessment)
        db.session.flush()

        # Customer user
        user = User(
            username=DEMO_USERNAME,
            role="customer",
            assessment_id=assessment.id,
        )
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()

        # Tools
        tool_objs = []
        for t in TOOLS:
            tool = ToolInventory(
                assessment_id=assessment.id,
                name=t["name"],
                vendor=t["vendor"],
                category=t["category"],
                notes=t["notes"],
                mapping_status="active",
            )
            db.session.add(tool)
            tool_objs.append(tool)
        db.session.flush()

        # Responses
        for (activity_id, current, target, notes) in RESPONSES:
            pillar = activity_id.split(".")[1]
            resp = Response(
                assessment_id=assessment.id,
                pillar=pillar,
                activity_id=activity_id,
                current_state_value=current,
                target_state_value=target,
                evidence_notes=notes,
            )
            db.session.add(resp)
        db.session.flush()

        # Tool → activity mappings
        for tool_idx, activity_ids in TOOL_MAPPINGS.items():
            tool = tool_objs[tool_idx]
            for aid in activity_ids:
                mapping = ToolActivityMapping(
                    tool_id=tool.id,
                    activity_id=aid,
                    source="ai_suggested",
                    ai_confidence="high",
                    ai_rationale="Mapped during demo data seeding.",
                )
                db.session.add(mapping)
        db.session.flush()

        # Pillar consultant annotations
        for pillar_id, notes in PILLAR_NOTES.items():
            score = AdminScore(
                assessment_id=assessment.id,
                pillar=pillar_id,
                gap_summary=notes["gap_summary"],
                consultant_recommendation=notes["consultant_recommendation"],
            )
            db.session.add(score)
        db.session.flush()

        # Gap findings
        now = datetime.now(timezone.utc)
        for f in FINDINGS:
            finding = GapFinding(
                assessment_id=assessment.id,
                pillar=f["pillar"],
                activity_id=f["activity_id"],
                severity=f["severity"],
                scrubbed_prompt="[demo — no prompt]",
                scrubbed_response=f["text"],
                rehydrated_response=f["text"],
                is_stale=False,
                generated_at=now,
            )
            db.session.add(finding)

        db.session.commit()

        print("✓ Demo assessment created.")
        print(f"\n  Organisation : {DEMO_ORG}")
        print(f"  Framework    : CISA Zero Trust Maturity Model")
        print(f"  Tools        : {len(TOOLS)} tools with mappings")
        print(f"  Activities   : {len(RESPONSES)} filled out")
        print(f"  Gap findings : {len(FINDINGS)} pre-generated")
        print(f"\nLogin at /resume with:")
        print(f"  Name/username : {DEMO_USERNAME}")
        print(f"  Password      : {DEMO_PASSWORD}")


if __name__ == "__main__":
    seed()
