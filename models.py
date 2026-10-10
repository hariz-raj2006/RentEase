"""Constants, validation, and helpers that build MongoDB documents."""
import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------- constants
PROPERTY_TYPES = ["Apartment", "Independent House", "Villa", "Room"]
FURNISHING_OPTIONS = ["Furnished", "Semi-Furnished", "Unfurnished"]
AVAILABILITY_OPTIONS = ["Available", "Rented"]
LISTING_STATUSES = ["pending", "approved", "rejected"]
ENQUIRY_STATUSES = ["Pending", "Contacted", "Closed"]
PUBLIC_ROLES = ["tenant", "owner"]          # "admin" can NOT be chosen publicly
AMENITY_OPTIONS = [
    "Parking", "Wi-Fi", "Air Conditioning", "Power Backup", "Lift",
    "Security", "Gym", "Swimming Pool", "Garden", "Balcony",
    "Water Supply 24x7", "Pet Friendly",
]


def _unsplash(photo_id):
    return f"https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w=900&q=70"


# (label, url). Used by the property form dropdown and by seed_data.py.
# If any image fails to load, script.js shows a CSS placeholder instead.
SAMPLE_IMAGES = [
    ("Modern apartment living room", _unsplash("photo-1502672260266-1c1ef2d93688")),
    ("City apartment building", _unsplash("photo-1545324418-cc1a3fa10c00")),
    ("Independent house with garden", _unsplash("photo-1568605114967-8130f3a36994")),
    ("Family home exterior", _unsplash("photo-1564013799919-ab600027ffc6")),
    ("Luxury villa", _unsplash("photo-1512917774080-9991f1c4c750")),
    ("Villa with pool", _unsplash("photo-1613490493576-7fde63acd811")),
    ("Cozy bedroom", _unsplash("photo-1505691938895-1758d7feb511")),
    ("Studio room", _unsplash("photo-1522708323590-d24dbb6b0267")),
    ("Bright apartment interior", _unsplash("photo-1560448204-e02f11c3d0e2")),
    ("Modern kitchen", _unsplash("photo-1484154218962-a197022b5858")),
]

# Starting values for the "Add property" form
PROPERTY_FORM_DEFAULTS = {
    "title": "", "description": "", "location": "", "rent": "",
    "property_type": "Apartment", "bedrooms": "1", "bathrooms": "1",
    "area_sqft": "", "furnishing": "Unfurnished", "amenities": [],
    "image_url": "", "availability": "Available",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ helpers
def utcnow():
    return datetime.now(timezone.utc)


def parse_object_id(value):
    """Turn a string into an ObjectId, or return None if it is not valid."""
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


def to_int(value):
    """Convert text to int, or return None if it is not a whole number."""
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def serialize(doc):
    """Copy a MongoDB document and add a string 'id' for use in templates/URLs."""
    if doc is None:
        return None
    result = dict(doc)
    result["id"] = str(result["_id"])
    return result


def serialize_list(docs):
    return [serialize(d) for d in docs]


# --------------------------------------------------------------- validation
def _check_name(name, errors):
    if not 2 <= len(name) <= 60:
        errors.append("Full name must be between 2 and 60 characters.")


def _clean_phone(raw, errors):
    phone = re.sub(r"[\s\-()]", "", (raw or "").strip())
    if not re.fullmatch(r"\+?\d{10,13}", phone):
        errors.append("Enter a valid phone number (10 to 13 digits).")
    return phone


def validate_registration(form):
    """Return (errors, cleaned_data) for the registration form."""
    errors = []
    name = form.get("name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "")
    confirm = form.get("confirm_password", "")
    role = form.get("role", "").strip()

    _check_name(name, errors)

    if not email or len(email) > 120 or not EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")

    phone = _clean_phone(form.get("phone", ""), errors)

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    elif not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        errors.append("Password must contain at least one letter and one number.")
    if password != confirm:
        errors.append("Passwords do not match.")

    # Only tenant and owner are allowed. Anything else (such as "admin") is rejected.
    if role not in PUBLIC_ROLES:
        errors.append("Please choose a valid account type (Tenant or Property Owner).")

    cleaned = {"name": name, "email": email, "phone": phone,
               "password": password, "role": role}
    return errors, cleaned


def validate_profile(form):
    errors = []
    name = form.get("name", "").strip()
    _check_name(name, errors)
    phone = _clean_phone(form.get("phone", ""), errors)
    return errors, {"name": name, "phone": phone}


def validate_property(form):
    """Return (errors, cleaned_data) for the owner's property form."""
    errors = []

    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    location = form.get("location", "").strip()
    property_type = form.get("property_type", "").strip()
    furnishing = form.get("furnishing", "").strip()
    availability = form.get("availability", "").strip()
    image_url = form.get("image_url", "").strip()

    if not 5 <= len(title) <= 100:
        errors.append("Title must be between 5 and 100 characters.")
    if not 20 <= len(description) <= 2000:
        errors.append("Description must be between 20 and 2000 characters.")
    if not 3 <= len(location) <= 100:
        errors.append("Location must be between 3 and 100 characters.")
    if property_type not in PROPERTY_TYPES:
        errors.append("Choose a valid property type.")
    if furnishing not in FURNISHING_OPTIONS:
        errors.append("Choose a valid furnishing status.")
    if availability not in AVAILABILITY_OPTIONS:
        errors.append("Choose a valid availability status.")

    rent = to_int(form.get("rent"))
    if rent is None or not 500 <= rent <= 1_000_000:
        errors.append("Monthly rent must be a number between 500 and 1,000,000.")

    bedrooms = to_int(form.get("bedrooms"))
    if bedrooms is None or not 0 <= bedrooms <= 20:
        errors.append("Bedrooms must be a number between 0 and 20.")

    bathrooms = to_int(form.get("bathrooms"))
    if bathrooms is None or not 0 <= bathrooms <= 20:
        errors.append("Bathrooms must be a number between 0 and 20.")

    area = to_int(form.get("area_sqft"))
    if area is None or not 50 <= area <= 100000:
        errors.append("Area must be a number between 50 and 100,000 sq ft.")

    # Keep only amenities that are in our allowed list
    amenities = [a for a in form.getlist("amenities") if a in AMENITY_OPTIONS]

    # Image: blank -> default sample image. Otherwise must be http(s) or /static/
    if not image_url:
        image_url = SAMPLE_IMAGES[0][1]
    elif len(image_url) > 500 or not (
        image_url.startswith(("http://", "https://")) or image_url.startswith("/static/")
    ):
        errors.append("Image URL must start with http://, https:// or /static/.")

    cleaned = {
        "title": title, "description": description, "location": location,
        "rent": rent, "property_type": property_type,
        "bedrooms": bedrooms, "bathrooms": bathrooms, "area_sqft": area,
        "furnishing": furnishing, "amenities": amenities,
        "image_url": image_url, "availability": availability,
    }
    return errors, cleaned


def validate_enquiry_message(message):
    message = (message or "").strip()
    errors = []
    if not 10 <= len(message) <= 1000:
        errors.append("Your message must be between 10 and 1000 characters.")
    return errors, message


def property_form_values(form):
    """Collect what the user typed so the form can be re-filled after an error."""
    values = {key: form.get(key, "") for key in PROPERTY_FORM_DEFAULTS if key != "amenities"}
    values["amenities"] = form.getlist("amenities")
    return values


# ------------------------------------------------------ document builders
def build_user_doc(cleaned, role=None):
    """Create a users document. The password is hashed, never stored as text."""
    return {
        "name": cleaned["name"],
        "email": cleaned["email"],
        "phone": cleaned["phone"],
        "password_hash": generate_password_hash(cleaned["password"]),
        "role": role or cleaned["role"],
        "created_at": utcnow(),
    }


def build_property_doc(cleaned, owner_id, status="pending"):
    doc = dict(cleaned)
    doc.update({
        "gallery": [],
        "owner_id": owner_id,
        "status": status,              # pending -> approved/rejected by admin
        "created_at": utcnow(),
    })
    return doc


def build_enquiry_doc(tenant_id, owner_id, property_id, message):
    return {
        "tenant_id": tenant_id,
        "owner_id": owner_id,
        "property_id": property_id,
        "message": message,
        "status": "Pending",
        "created_at": utcnow(),
    }