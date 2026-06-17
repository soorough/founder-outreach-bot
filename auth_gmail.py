"""Run once locally: python auth_gmail.py
Opens a browser, authorizes Gmail compose scope, writes token.json."""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def main():
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_path, "w", encoding="utf-8") as handle:
        handle.write(creds.to_json())
    print(f"Wrote {token_path}")


if __name__ == "__main__":
    main()
