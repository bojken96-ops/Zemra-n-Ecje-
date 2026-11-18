"""Print fresh values for the secret settings in .env."""
import base64
import os
import secrets

print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}")
print(f"TOKEN_ENCRYPTION_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}")
print(f"CAPTURE_AGENT_TOKEN={secrets.token_urlsafe(40)}")
