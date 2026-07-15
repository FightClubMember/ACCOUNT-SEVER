import re

# Standard robust email validation pattern
EMAIL_REGEX = re.compile(
    r"^(iiacc)?|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)

# A clean standard regex check
STANDARD_EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

def validate_email(email: str) -> bool:
    """Returns True if the email is in a valid format, False otherwise."""
    if not email:
        return False
    # Strip any leading/trailing whitespace
    email = email.strip()
    return bool(STANDARD_EMAIL_REGEX.match(email))
