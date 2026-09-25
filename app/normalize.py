"""Normalizes spoken/loosely-formatted input into clean field values.
Shared by the REST API (Pydantic validators) and the voice agent's tool
calls, so a caller saying things like "January fifth nineteen ninety" or
"john dot smith at gmail dot com" ends up stored the same way a typed
API request would.
"""
import re
from datetime import date, datetime

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
VALID_STATE_CODES = set(US_STATES.values())

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def normalize_name(raw: str) -> str:
    return " ".join(raw.strip().split())


def normalize_phone(raw: str) -> str:
    """Extracts 10 US digits from any spoken/typed format, e.g.
    "(555) 123-4567", "five five five, one two three, four five six seven"."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_zip(raw: str) -> str:
    digits = re.sub(r"[^\d-]", "", raw.strip())
    return digits


def normalize_state(raw: str) -> str:
    cleaned = raw.strip().upper()
    if cleaned in VALID_STATE_CODES:
        return cleaned
    return US_STATES.get(raw.strip().lower(), raw.strip())


def normalize_email(raw: str) -> str:
    """Handles spoken email dictation: "john dot smith at gmail dot com"."""
    cleaned = raw.strip().lower()
    if "@" not in cleaned:
        cleaned = re.sub(r"\s+at\s+", "@", cleaned)
    cleaned = re.sub(r"\s+dot\s+", ".", cleaned)
    cleaned = cleaned.replace(" ", "")
    return cleaned


def normalize_dob(raw: str) -> date | None:
    """Accepts MM/DD/YYYY, YYYY-MM-DD, or spoken forms like
    "January 5th, 1990" / "5 January 1990". Returns None if unparseable."""
    raw = raw.strip()

    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw.lower())
    cleaned = cleaned.replace(",", "")
    tokens = cleaned.split()

    month = day = year = None
    for tok in tokens:
        if tok in MONTHS:
            month = MONTHS[tok]
        elif tok.isdigit():
            num = int(tok)
            if num > 31:
                year = num
            elif 1 <= num <= 31 and day is None:
                day = num

    if month and day and year:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


# --- validate_* functions: normalize + enforce the field's rules,
# raising ValueError with a caller-facing message on failure. Shared by
# the REST API schemas and the voice agent's submit_patient tool, so a
# bad value gets the exact same message and re-ask either way.

def validate_name(raw: str, field_label: str) -> str:
    cleaned = normalize_name(raw)
    if not re.fullmatch(r"[A-Za-z][A-Za-z'\- ]{0,49}", cleaned):
        raise ValueError(f"{field_label} must be 1-50 letters (hyphens/apostrophes allowed)")
    return cleaned


def validate_dob(raw: str | date) -> date:
    parsed = raw if isinstance(raw, date) else normalize_dob(str(raw))
    if parsed is None:
        raise ValueError("date of birth must be a valid date, e.g. MM/DD/YYYY")
    if parsed > date.today():
        raise ValueError("date of birth cannot be in the future")
    return parsed


def validate_phone(raw: str, field_label: str = "phone number") -> str:
    digits = normalize_phone(raw)
    if len(digits) != 10:
        raise ValueError(f"{field_label} must have exactly 10 digits")
    return digits


def validate_email_field(raw: str) -> str:
    cleaned = normalize_email(raw)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned):
        raise ValueError("email address doesn't look valid")
    return cleaned


def validate_state(raw: str) -> str:
    code = normalize_state(raw)
    if code not in VALID_STATE_CODES:
        raise ValueError("state must be a valid US state (2-letter abbreviation or full name)")
    return code


def validate_zip(raw: str) -> str:
    cleaned = normalize_zip(raw)
    if not re.fullmatch(r"\d{5}(-\d{4})?", cleaned):
        raise ValueError("zip code must be 5 digits or ZIP+4 format (e.g. 12345 or 12345-6789)")
    return cleaned


def validate_city(raw: str) -> str:
    cleaned = raw.strip()
    if not (1 <= len(cleaned) <= 100):
        raise ValueError("city must be 1-100 characters")
    return cleaned


def validate_member_id(raw: str) -> str:
    cleaned = raw.strip()
    if not re.fullmatch(r"[A-Za-z0-9]+", cleaned):
        raise ValueError("insurance member ID must be alphanumeric")
    return cleaned
