import json
import logging
from typing import Any
import gspread
from google.oauth2.service_account import Credentials
from app.core.config import settings

logger = logging.getLogger(__name__)

# Required scopes for Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def _get_client() -> gspread.Client:
    """Authenticate and return gspread client."""
    credentials = Credentials.from_service_account_file(
        settings.google_sheets_credentials_file,
        scopes=SCOPES
    )
    return gspread.authorize(credentials)

def export_to_google_sheets(candidates: list[dict[str, Any]], sheet_id: str, tab_name: str = "Candidates") -> str:
    """
    Exports a list of candidates to a Google Sheet.
    Returns the URL of the Google Sheet upon success.
    """
    if not candidates:
        logger.warning("No candidates provided for export.")
        return ""

    if not sheet_id:
        logger.error("No Google Sheet ID provided.")
        return ""

    try:
        # Authenticate
        client = _get_client()
        
        # Open the spreadsheet by ID
        spreadsheet = client.open_by_key(sheet_id)
        
        # Open or create the worksheet (tab)
        try:
            worksheet = spreadsheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=20)
            
        # Define headers exactly as requested
        headers = [
            "Timestamp",
            "Name",
            "Title",
            "Location",
            "Email",
            "LinkedIn",
            "Twitter/X",
            "Instagram",
            "ArtStation",
            "Portfolio",
            "Top Works",
            "Experience",
            "Years Exp",
            "Outreach Platform",
            "Message Sent",
            "Status",
            "Notes"
        ]
        
        # Get existing data to avoid overwriting and check if headers exist
        existing_data = worksheet.get_all_values()
        
        if not existing_data:
            # Add headers if sheet is completely empty
            worksheet.append_row(headers)
            
            # Add descriptions/notes row right below the headers
            descriptions = [
                "Khi được add", # Timestamp
                "Full name", # Name
                "Current position", # Title
                "City, Country", # Location
                "Nếu có", # Email
                "", # LinkedIn
                "", # Twitter/X
                "", # Instagram
                "", # ArtStation
                "Main portfolio link", # Portfolio
                "3-5 links, comma separated", # Top Works
                "Notable companies/projects", # Experience
                "Estimate", # Years Exp
                "LinkedIn/Email/Twitter/IG", # Outreach Platform
                "", # Message Sent
                "Pending/Replied/No Response/Not Interested", # Status
                "Free text cho follow-up" # Notes
            ]
            worksheet.append_row(descriptions)
        
        # Prepare rows to append
        rows_to_append = []
        for c in candidates:
            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Formatting lists
            top_works = ", ".join(c.get("top_works") or [])
            
            # Combine current company and previous companies or experience summary for experience
            experience_parts = []
            if c.get("current_company"):
                experience_parts.append(f"Current: {c.get('current_company')}")
            if c.get("experience_summary"):
                experience_parts.append(str(c.get("experience_summary")).strip())
            if c.get("notable_projects"):
                experience_parts.extend(c.get("notable_projects")[:2])
            experience = " | ".join(experience_parts)[:500]
            
            # Logic for outreach platform (default to source platform)
            source_platform = c.get("source_platform", "")
            if source_platform == "linkedin":
                outreach = "LinkedIn"
            elif source_platform == "instagram":
                outreach = "Instagram"
            elif source_platform in ("x", "twitter"):
                outreach = "Twitter/X"
            elif source_platform == "artstation":
                outreach = "Email"
            else:
                outreach = "Email"
                
            row = [
                timestamp,
                c.get("full_name", ""),
                str(c.get("title", ""))[:200],
                c.get("location", ""),
                c.get("email", ""),
                c.get("linkedin_url", ""),
                c.get("x_url", ""),
                c.get("instagram_url", ""),
                c.get("artstation_url", ""),
                c.get("portfolio_url", ""),
                top_works,
                experience,
                str(c.get("years_exp_estimate") or ""),
                outreach,
                "", # Message Sent
                "Pending", # Status
                ""  # Notes
            ]
            rows_to_append.append(row)
            
        if rows_to_append:
            worksheet.append_rows(rows_to_append)
            logger.info(f"Appended {len(rows_to_append)} rows to Google Sheet {sheet_id}")
            
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={worksheet.id}"

    except Exception as e:
        logger.error(f"Failed to export to Google Sheets: {e}")
        raise
