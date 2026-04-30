"""
First-time .env setup helper — called by start.bat and start.sh.
Uses getpass so the password is never echoed to the terminal.
"""
import sys
import secrets
import getpass

try:
    from werkzeug.security import generate_password_hash
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "werkzeug", "--quiet"])
    from werkzeug.security import generate_password_hash

print()
print("  ------------------------------------------------")
print("  First-time setup")
print("  ------------------------------------------------")
print()
print("  You only need to do this once.")
print("  A .env file will be created in this folder.")
print()

# Admin password
print("  Admin password (minimum 12 characters):")
while True:
    password = getpass.getpass("  Password: ")
    if len(password) >= 12:
        break
    print("  Please use at least 12 characters.")

confirm = getpass.getpass("  Confirm:  ")
if password != confirm:
    print("  Error: Passwords do not match.")
    sys.exit(1)

print()
print("  Anthropic API key (optional — press Enter to skip)")
print("  Required for AI gap findings and ATT&CK coverage reports.")
print("  Get one at https://console.anthropic.com")
api_key = input("  API key: ").strip()
print()

secret  = secrets.token_hex(32)
pw_hash = generate_password_hash(password)

with open(".env", "w") as f:
    f.write(f"FLASK_SECRET_KEY={secret}\n")
    f.write(f"ADMIN_PASSWORD_HASH={pw_hash}\n")
    f.write(f"ANTHROPIC_API_KEY={api_key}\n")
    f.write("DATABASE_URL=sqlite:///instance/assessments.db\n")
    f.write("ANTHROPIC_MODEL=claude-sonnet-4-6\n")
    f.write("FORCE_HTTPS=false\n")

print(f"  [OK] Saved to .env  (secret_key={secret[:8]}...)")
print()
print("  To enable SharePoint upload, add these to .env:")
print("    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET")
print("    SHAREPOINT_SITE_ID, SHAREPOINT_DRIVE_ID")
print("  See docs/guides/Setup and SharePoint Integration Guide.docx for details.")
print("  ------------------------------------------------")
