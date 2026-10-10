"""Adds sample data to MongoDB and creates the administrator account.

Run these from the RentEase folder with the virtual environment active:

    py seed_data.py          -> sample owners, 1 sample tenant, 13 properties
    py seed_data.py --admin  -> create an administrator (asks you for details)

No passwords are written in this file. You type them in when asked, and they
are hashed before being saved.
"""
import argparse
import sys
from getpass import getpass

from pymongo.errors import PyMongoError

import models
from database import ensure_indexes, get_db

SAMPLE_OWNERS = [
    {"name": "Ananya Rao", "email": "ananya.owner@rentease.example", "phone": "9876500001"},
    {"name": "Rahul Verma", "email": "rahul.owner@rentease.example", "phone": "9876500002"},
    {"name": "Meera Iyer", "email": "meera.owner@rentease.example", "phone": "9876500003"},
]

SAMPLE_TENANT = {"name": "Karthik Menon", "email": "karthik.tenant@rentease.example",
                 "phone": "9876500004"}

# "owner" is an index into SAMPLE_OWNERS, "img" is an index into models.SAMPLE_IMAGES
SAMPLE_PROPERTIES = [
    {"title": "Sunrise Heights 2BHK Apartment", "location": "Velachery, Chennai",
     "rent": 24000, "property_type": "Apartment", "bedrooms": 2, "bathrooms": 2,
     "area_sqft": 1050, "furnishing": "Semi-Furnished",
     "amenities": ["Parking", "Lift", "Security", "Power Backup"],
     "description": "Bright 2BHK on the 5th floor with cross ventilation, a modular "
                    "kitchen and covered parking. Close to schools, shops and the MRTS station.",
     "img": 0, "owner": 0, "availability": "Available", "status": "approved"},

    {"title": "Lakeview Studio Apartment", "location": "Indiranagar, Bengaluru",
     "rent": 18000, "property_type": "Apartment", "bedrooms": 1, "bathrooms": 1,
     "area_sqft": 520, "furnishing": "Furnished",
     "amenities": ["Wi-Fi", "Air Conditioning", "Lift", "Security"],
     "description": "Fully furnished studio ideal for working professionals. Includes a "
                    "queen bed, wardrobe, study desk, AC and high-speed Wi-Fi.",
     "img": 1, "owner": 1, "availability": "Available", "status": "approved"},

    {"title": "Green Gables Independent House", "location": "Saibaba Colony, Coimbatore",
     "rent": 28000, "property_type": "Independent House", "bedrooms": 3, "bathrooms": 3,
     "area_sqft": 1800, "furnishing": "Semi-Furnished",
     "amenities": ["Parking", "Garden", "Water Supply 24x7", "Power Backup"],
     "description": "Spacious independent house with a front garden, two-car parking and "
                    "a large living area. Quiet residential street, perfect for families.",
     "img": 2, "owner": 2, "availability": "Available", "status": "approved"},

    {"title": "Palm Grove Beachside Villa", "location": "ECR, Chennai",
     "rent": 85000, "property_type": "Villa", "bedrooms": 4, "bathrooms": 5,
     "area_sqft": 3800, "furnishing": "Furnished",
     "amenities": ["Swimming Pool", "Garden", "Parking", "Security", "Air Conditioning", "Gym"],
     "description": "Premium villa with a private pool, landscaped garden and home gym. "
                    "Walking distance to the beach with 24-hour gated security.",
     "img": 5, "owner": 0, "availability": "Available", "status": "approved"},

    {"title": "Cozy Room Near Tech Park", "location": "Gachibowli, Hyderabad",
     "rent": 8500, "property_type": "Room", "bedrooms": 1, "bathrooms": 1,
     "area_sqft": 180, "furnishing": "Furnished",
     "amenities": ["Wi-Fi", "Air Conditioning", "Water Supply 24x7"],
     "description": "Neat private room in a shared flat, 10 minutes from the main tech "
                    "park. Includes AC, bed, wardrobe, Wi-Fi and a shared kitchen.",
     "img": 6, "owner": 1, "availability": "Available", "status": "approved"},

    {"title": "Skyline 3BHK with Balcony", "location": "Baner, Pune",
     "rent": 35000, "property_type": "Apartment", "bedrooms": 3, "bathrooms": 3,
     "area_sqft": 1450, "furnishing": "Semi-Furnished",
     "amenities": ["Parking", "Lift", "Gym", "Balcony", "Security"],
     "description": "Modern 3BHK on a high floor with a wide balcony and city views. "
                    "The society has a clubhouse, gym and children's play area.",
     "img": 8, "owner": 2, "availability": "Available", "status": "approved"},

    {"title": "Heritage Courtyard House", "location": "Anna Nagar, Madurai",
     "rent": 19000, "property_type": "Independent House", "bedrooms": 3, "bathrooms": 2,
     "area_sqft": 1600, "furnishing": "Unfurnished",
     "amenities": ["Parking", "Garden", "Water Supply 24x7", "Pet Friendly"],
     "description": "Traditional-style house with an open courtyard, tiled floors and "
                    "plenty of natural light. Pets are welcome.",
     "img": 3, "owner": 0, "availability": "Available", "status": "approved"},

    {"title": "Student Friendly Single Room", "location": "Guindy, Chennai",
     "rent": 6000, "property_type": "Room", "bedrooms": 1, "bathrooms": 1,
     "area_sqft": 140, "furnishing": "Unfurnished",
     "amenities": ["Wi-Fi", "Water Supply 24x7", "Power Backup"],
     "description": "Affordable single room close to colleges and the railway station. "
                    "Attached bathroom and Wi-Fi included in the rent.",
     "img": 7, "owner": 1, "availability": "Available", "status": "approved"},

    {"title": "Hillcrest Luxury Villa", "location": "Whitefield, Bengaluru",
     "rent": 120000, "property_type": "Villa", "bedrooms": 5, "bathrooms": 6,
     "area_sqft": 5200, "furnishing": "Furnished",
     "amenities": ["Swimming Pool", "Gym", "Garden", "Parking", "Security",
                   "Power Backup", "Air Conditioning"],
     "description": "Grand five-bedroom villa in a gated community with a pool, private "
                    "gym, home office and a spacious lawn. Designer interiors throughout.",
     "img": 4, "owner": 2, "availability": "Available", "status": "approved"},

    {"title": "Compact 1BHK Near Metro", "location": "Edappally, Kochi",
     "rent": 14500, "property_type": "Apartment", "bedrooms": 1, "bathrooms": 1,
     "area_sqft": 640, "furnishing": "Semi-Furnished",
     "amenities": ["Lift", "Parking", "Security", "Balcony"],
     "description": "Well-planned 1BHK five minutes from the metro station. Includes "
                    "a modular kitchen, wardrobes and a small balcony.",
     "img": 1, "owner": 0, "availability": "Available", "status": "approved"},

    {"title": "Garden Cottage with Pet Space", "location": "Kothrud, Pune",
     "rent": 26000, "property_type": "Independent House", "bedrooms": 2, "bathrooms": 2,
     "area_sqft": 1200, "furnishing": "Semi-Furnished",
     "amenities": ["Garden", "Pet Friendly", "Parking", "Water Supply 24x7"],
     "description": "Charming cottage with a private garden and a fenced pet area. "
                    "Quiet lane, close to cafes and a weekend market.",
     "img": 9, "owner": 1, "availability": "Available", "status": "approved"},

    {"title": "Executive Furnished 2BHK", "location": "Hitech City, Hyderabad",
     "rent": 32000, "property_type": "Apartment", "bedrooms": 2, "bathrooms": 2,
     "area_sqft": 1200, "furnishing": "Furnished",
     "amenities": ["Wi-Fi", "Air Conditioning", "Gym", "Lift", "Swimming Pool"],
     "description": "Fully furnished 2BHK in a premium tower with a rooftop pool and "
                    "gym. Walkable to major IT offices. Currently rented out.",
     "img": 8, "owner": 2, "availability": "Rented", "status": "approved"},

    # Waiting for admin approval, so you can test the approve/reject buttons
    {"title": "New Seaside Apartment (Awaiting Review)", "location": "Besant Nagar, Chennai",
     "rent": 30000, "property_type": "Apartment", "bedrooms": 2, "bathrooms": 2,
     "area_sqft": 1100, "furnishing": "Semi-Furnished",
     "amenities": ["Lift", "Parking", "Balcony"],
     "description": "Newly built apartment a short walk from the beach, with a sea-facing "
                    "balcony and covered parking. Waiting for admin approval.",
     "img": 0, "owner": 0, "availability": "Available", "status": "pending"},
]


def ask_password(label="Password"):
    """Ask for a password twice (hidden while typing) until it passes our rules."""
    while True:
        password = getpass(f"{label}: ")
        confirm = getpass("Confirm password: ")
        errors, _ = models.validate_registration({
            "name": "Seed User", "email": "seed@rentease.example", "phone": "9876543210",
            "password": password, "confirm_password": confirm, "role": "tenant"})
        problems = [e for e in errors if e.startswith("Password")]
        if not problems:
            return password
        print("  ->", " ".join(problems))


def get_or_create_user(db, info, password, role):
    """Return (user_id, created_flag). Existing users are left unchanged."""
    existing = db.users.find_one({"email": info["email"]})
    if existing:
        return existing["_id"], False
    cleaned = dict(info, password=password, role=role)
    result = db.users.insert_one(models.build_user_doc(cleaned, role=role))
    return result.inserted_id, True


def seed_samples():
    db = get_db()
    print("Sample accounts need ONE shared password (used for the 3 owners and 1 tenant).")
    print("Choose one you will remember: at least 8 characters, with a letter and a number.\n")
    password = ask_password("Sample account password")

    owner_ids = []
    for info in SAMPLE_OWNERS:
        owner_id, created = get_or_create_user(db, info, password, "owner")
        owner_ids.append(owner_id)
        print(f"  owner  {info['email']:<34} {'created' if created else 'already existed'}")

    _, created = get_or_create_user(db, SAMPLE_TENANT, password, "tenant")
    print(f"  tenant {SAMPLE_TENANT['email']:<34} {'created' if created else 'already existed'}")

    added = 0
    fields = ("title", "description", "location", "rent", "property_type", "bedrooms",
              "bathrooms", "area_sqft", "furnishing", "amenities", "availability")
    for item in SAMPLE_PROPERTIES:
        owner_id = owner_ids[item["owner"]]
        if db.properties.find_one({"title": item["title"], "owner_id": owner_id}):
            continue                                   # already seeded
        cleaned = {key: item[key] for key in fields}
        cleaned["image_url"] = models.SAMPLE_IMAGES[item["img"]][1]
        doc = models.build_property_doc(cleaned, owner_id, status=item["status"])
        count = len(models.SAMPLE_IMAGES)
        doc["gallery"] = [models.SAMPLE_IMAGES[(item["img"] + step) % count][1]
                          for step in (1, 2)]
        db.properties.insert_one(doc)
        added += 1

    print(f"\nDone. {added} new properties added.")
    print("Owner logins: ananya.owner@, rahul.owner@, meera.owner@ rentease.example")
    print("Tenant login: karthik.tenant@rentease.example")


def create_admin():
    db = get_db()
    print("Create an administrator account (this is the ONLY way to make an admin).\n")
    name = input("Full name: ").strip()
    email = input("Email: ").strip().lower()
    phone = input("Phone (10 digits): ").strip()
    password = ask_password("Admin password")

    errors, cleaned = models.validate_registration({
        "name": name, "email": email, "phone": phone,
        "password": password, "confirm_password": password, "role": "tenant"})
    if errors:
        print("\nCould not create the admin:")
        for message in errors:
            print("  -", message)
        sys.exit(1)

    if db.users.find_one({"email": cleaned["email"]}):
        print("\nAn account with that email already exists. Nothing was changed.")
        sys.exit(1)

    db.users.insert_one(models.build_user_doc(cleaned, role="admin"))
    print(f"\nAdministrator created. Log in at /login with {cleaned['email']}")


def main():
    parser = argparse.ArgumentParser(description="RentEase seed script")
    parser.add_argument("--admin", action="store_true",
                        help="create an administrator account instead of sample data")
    args = parser.parse_args()

    try:
        ensure_indexes()
        if args.admin:
            create_admin()
        else:
            seed_samples()
    except PyMongoError as exc:
        print("\n[!] Database error:", type(exc).__name__)
        print("    Check MONGO_URI in .env and your Atlas Network Access settings.")
        sys.exit(1)


if __name__ == "__main__":
    main()