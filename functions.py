"""
Calendar Functions for the Scheduler Agent
Helper functions and Google Calendar API integration
"""

from datetime import datetime, timedelta
import os
import json
import pytz

# Google Calendar imports
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Default timezone (can be overridden by env var)
DEFAULT_TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "UTC")


CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", os.getenv("GOOGLE_CALENDAR_USER_EMAIL", "primary"))


def get_calendar_service():
    """
    Initialize and return Google Calendar service.
    
    Supports three authentication methods (in order of priority):
    1. Service Account File: Set GOOGLE_SERVICE_ACCOUNT_FILE env var with path to JSON file
    2. Service Account JSON: Set GOOGLE_SERVICE_ACCOUNT_JSON env var with JSON string
    3. OAuth: Use credentials.json file and token.json for user auth
    """
    creds = None
    
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if service_account_file and os.path.exists(service_account_file):
        try:
            creds = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=SCOPES
            )
            delegate_email = os.getenv("GOOGLE_CALENDAR_USER_EMAIL")
            if delegate_email and not delegate_email.endswith("@gmail.com"):
                creds = creds.with_subject(delegate_email)
                print(f"✓ Authenticated with service account file (delegating to {delegate_email})")
            else:
                if delegate_email:
                    print(f"⚠️  Skipping delegation for Gmail account. Share your calendar with the service account instead.")
                print(f"✓ Authenticated with service account file: {service_account_file}")
        except Exception as e:
            print(f"Service account file auth failed: {e}")
    
    if not creds:
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if service_account_json:
            try:
                service_info = json.loads(service_account_json)
                creds = service_account.Credentials.from_service_account_info(
                    service_info, scopes=SCOPES
                )

                delegate_email = os.getenv("GOOGLE_CALENDAR_USER_EMAIL")
                if delegate_email and not delegate_email.endswith("@gmail.com"):
                    creds = creds.with_subject(delegate_email)
                    print(f"✓ Authenticated with service account JSON (delegating to {delegate_email})")
                else:
                    if delegate_email:
                        print(f"⚠️  Skipping delegation for Gmail account. Share your calendar with the service account instead.")
                    print("✓ Authenticated with service account JSON")
            except Exception as e:
                print(f"Service account JSON auth failed: {e}")
    

    if not creds:
        token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists(credentials_path):
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
    
    if not creds:
        raise ValueError(
            "No valid Google Calendar credentials found. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON env var, "
            "or provide credentials.json file."
        )
    
    return build('calendar', 'v3', credentials=creds)


def parse_datetime(dt_string: str, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """Parse various datetime string formats into a datetime object."""
    tz = pytz.timezone(timezone)
    

    for fmt in [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(dt_string, fmt)
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            return dt
        except ValueError:
            continue
    
    raise ValueError(f"Could not parse datetime: {dt_string}")


def format_datetime_for_api(dt: datetime) -> str:
    """Format datetime for Google Calendar API."""
    return dt.isoformat()
