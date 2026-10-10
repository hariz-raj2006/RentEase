"""Automated tests for RentEase.

HOW TO RUN (from the RentEase folder, virtual environment active):

    py -m pytest -v

SAFETY: every test automatically swaps the real MongoDB connection for
"mongomock", a fake database that lives only in memory. Your MongoDB Atlas
data is never read or changed by these tests.
"""
import sys
from pathlib import Path

# Make "import app" work no matter where pytest is started from
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mongomock
import pytest

import database
import models
from app import app as flask_app

PASSWORD = "Passw0rd1"          # a password that passes our rules (test use only)
MISSING_ID = "000000000000000000000000"   # a valid-looking id that does not exist


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def db():
    """Runs before EVERY test: a fresh, empty, in-memory database."""
    fake_client = mongomock.MongoClient()
    test_db = database.init_db(client=fake_client, db_name="rentease_test")
    database.ensure_indexes()
    yield test_db


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return flask_app.test_client()


# ------------------------------------------------------------------- helpers
def make_user(db, role="tenant", email=None, password=PASSWORD):
    email = email or f"{role}@test.example"
    cleaned = {"name": f"Test {role.title()}", "email": email,
               "phone": "9876543210", "password": password, "role": role}
    return db.users.insert_one(models.build_user_doc(cleaned, role=role)).inserted_id


def make_property(db, owner_id, title="Test Flat", rent=20000, status="approved",
                  availability="Available", location="Chennai",
                  property_type="Apartment", bedrooms=2):
    cleaned = {
        "title": title, "description": "A nice test property with enough text.",
        "location": location, "rent": rent, "property_type": property_type,
        "bedrooms": bedrooms, "bathrooms": 1, "area_sqft": 900,
        "furnishing": "Unfurnished", "amenities": ["Parking"],
        "image_url": models.SAMPLE_IMAGES[0][1], "availability": availability,
    }
    doc = models.build_property_doc(cleaned, owner_id, status=status)
    return db.properties.insert_one(doc).inserted_id


def login(client, email, password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def register_payload(**overrides):
    data = {"name": "Priya Sharma", "email": "priya@test.example",
            "phone": "9876543210", "password": PASSWORD,
            "confirm_password": PASSWORD, "role": "tenant"}
    data.update(overrides)
    return data


# ============================================================== homepage
def test_homepage_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"RentEase" in response.data
    assert b"Find a Place You" in response.data


def test_homepage_works_with_no_properties(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"No properties listed yet" in response.data


# ========================================================== registration
def test_register_page_loads(client):
    assert client.get("/register").status_code == 200


def test_register_success_hashes_password(client, db):
    response = client.post("/register", data=register_payload())
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    user = db.users.find_one({"email": "priya@test.example"})
    assert user is not None
    assert user["role"] == "tenant"
    assert user["password_hash"] != PASSWORD          # never stored as plain text
    assert PASSWORD not in user["password_hash"]


def test_register_as_owner_is_allowed(client, db):
    client.post("/register", data=register_payload(role="owner"))
    assert db.users.find_one({"email": "priya@test.example"})["role"] == "owner"


def test_register_password_mismatch(client, db):
    response = client.post("/register", data=register_payload(confirm_password="Different1"))
    assert response.status_code == 200
    assert b"Passwords do not match" in response.data
    assert db.users.count_documents({}) == 0


def test_register_weak_password(client, db):
    response = client.post("/register",
                           data=register_payload(password="short", confirm_password="short"))
    assert b"at least 8 characters" in response.data
    assert db.users.count_documents({}) == 0


def test_register_password_needs_letter_and_number(client, db):
    response = client.post("/register", data=register_payload(
        password="onlyletters", confirm_password="onlyletters"))
    assert b"at least one letter and one number" in response.data
    assert db.users.count_documents({}) == 0


def test_register_invalid_email(client, db):
    response = client.post("/register", data=register_payload(email="not-an-email"))
    assert b"valid email" in response.data
    assert db.users.count_documents({}) == 0


def test_register_invalid_phone(client, db):
    response = client.post("/register", data=register_payload(phone="123"))
    assert b"valid phone number" in response.data
    assert db.users.count_documents({}) == 0


def test_register_missing_fields(client, db):
    response = client.post("/register", data={})
    assert response.status_code == 200
    assert db.users.count_documents({}) == 0


def test_register_cannot_choose_admin_role(client, db):
    response = client.post("/register", data=register_payload(role="admin"))
    assert response.status_code == 200
    assert b"valid account type" in response.data
    assert db.users.count_documents({}) == 0


def test_register_duplicate_email(client, db):
    make_user(db, "tenant", email="priya@test.example")
    response = client.post("/register", data=register_payload())
    assert b"already exists" in response.data
    assert db.users.count_documents({}) == 1


def test_duplicate_email_is_case_insensitive(client, db):
    make_user(db, "tenant", email="priya@test.example")
    response = client.post("/register", data=register_payload(email="PRIYA@Test.Example"))
    assert b"already exists" in response.data
    assert db.users.count_documents({}) == 1


# ================================================================= login
def test_login_page_loads(client):
    assert client.get("/login").status_code == 200


def test_login_wrong_password(client, db):
    make_user(db, "tenant", email="t@test.example")
    response = login(client, "t@test.example", "WrongPass1")
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_login_unknown_email(client):
    response = login(client, "nobody@test.example")
    assert b"Invalid email or password" in response.data


def test_login_empty_fields(client):
    response = client.post("/login", data={"email": "", "password": ""})
    assert b"enter your email and password" in response.data


def test_login_success_opens_dashboard(client, db):
    make_user(db, "tenant", email="t@test.example")
    response = login(client, "t@test.example")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert client.get("/dashboard").status_code == 200


def test_owner_login_goes_to_owner_dashboard(client, db):
    make_user(db, "owner", email="o@test.example")
    login(client, "o@test.example")
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/owner/dashboard")


def test_login_blocks_open_redirect(client, db):
    make_user(db, "tenant", email="t@test.example")
    response = client.post("/login?next=//evil.example",
                           data={"email": "t@test.example", "password": PASSWORD})
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]


def test_logout_clears_session(client, db):
    make_user(db, "tenant", email="t@test.example")
    login(client, "t@test.example")
    assert client.post("/logout").status_code == 302
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_logout_requires_post(client):
    assert client.get("/logout").status_code == 405


# ================================================ unauthorized access
PROTECTED_PAGES = [
    "/dashboard", "/profile", "/wishlist", "/enquiries",
    "/owner/dashboard", "/owner/enquiries", "/owner/property/add",
    "/admin/dashboard", "/admin/users",
]


@pytest.mark.parametrize("path", PROTECTED_PAGES)
def test_anonymous_users_are_sent_to_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_wishlist_toggle_json_gives_401(client, db):
    owner = make_user(db, "owner")
    pid = make_property(db, owner)
    response = client.post(f"/wishlist/toggle/{pid}", headers={"X-Requested-With": "fetch"})
    assert response.status_code == 401
    assert response.get_json()["ok"] is False


# ================================================ role-based protection
@pytest.mark.parametrize("role, path", [
    ("tenant", "/owner/dashboard"),
    ("tenant", "/owner/property/add"),
    ("tenant", "/owner/enquiries"),
    ("tenant", "/admin/dashboard"),
    ("tenant", "/admin/users"),
    ("owner", "/admin/dashboard"),
    ("owner", "/admin/users"),
    ("owner", "/wishlist"),
    ("owner", "/enquiries"),
    ("admin", "/owner/dashboard"),
    ("admin", "/wishlist"),
])
def test_wrong_role_gets_403(client, db, role, path):
    make_user(db, role, email="x@test.example")
    login(client, "x@test.example")
    response = client.get(path)
    assert response.status_code == 403
    assert b"Access Denied" in response.data


def test_each_role_reaches_its_own_dashboard(client, db):
    for role, path in [("tenant", "/dashboard"), ("owner", "/owner/dashboard"),
                       ("admin", "/admin/dashboard")]:
        client.post("/logout")
        make_user(db, role, email=f"{role}@test.example")
        login(client, f"{role}@test.example")
        assert client.get(path).status_code == 200


def test_tenant_cannot_use_admin_approve_action(client, db):
    owner = make_user(db, "owner")
    pid = make_property(db, owner, status="pending")
    make_user(db, "tenant", email="t@test.example")
    login(client, "t@test.example")
    response = client.post(f"/admin/property/{pid}/status", data={"action": "approve"})
    assert response.status_code == 403
    assert db.properties.find_one({"_id": pid})["status"] == "pending"


def test_tenant_cannot_delete_via_owner_route(client, db):
    owner = make_user(db, "owner")
    pid = make_property(db, owner)
    make_user(db, "tenant", email="t@test.example")
    login(client, "t@test.example")
    assert client.post(f"/owner/property/delete/{pid}").status_code == 403
    assert db.properties.count_documents({"_id": pid}) == 1


# ===================================================== property ownership
def test_owner_cannot_edit_another_owners_property(client, db):
    owner1 = make_user(db, "owner", email="o1@test.example")
    make_user(db, "owner", email="o2@test.example")
    pid = make_property(db, owner1)
    login(client, "o2@test.example")
    assert client.get(f"/owner/property/edit/{pid}").status_code == 404


def test_owner_cannot_delete_another_owners_property(client, db):
    owner1 = make_user(db, "owner", email="o1@test.example")
    make_user(db, "owner", email="o2@test.example")
    pid = make_property(db, owner1)
    login(client, "o2@test.example")
    assert client.post(f"/owner/property/delete/{pid}").status_code == 404
    assert db.properties.count_documents({"_id": pid}) == 1


def test_owner_can_delete_own_property_and_related_data(client, db):
    owner = make_user(db, "owner", email="o@test.example")
    tenant = make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner)
    db.wishlists.insert_one({"user_id": tenant, "property_id": pid, "created_at": models.utcnow()})
    db.enquiries.insert_one(models.build_enquiry_doc(tenant, owner, pid, "Is this available?"))

    login(client, "o@test.example")
    assert client.post(f"/owner/property/delete/{pid}").status_code == 302
    assert db.properties.count_documents({}) == 0
    assert db.wishlists.count_documents({}) == 0
    assert db.enquiries.count_documents({}) == 0


def test_owner_adds_property_as_pending(client, db):
    make_user(db, "owner", email="o@test.example")
    login(client, "o@test.example")
    response = client.post("/owner/property/add", data={
        "title": "Brand New Flat", "description": "A lovely flat with plenty of light and space.",
        "location": "Adyar, Chennai", "rent": "22000", "property_type": "Apartment",
        "bedrooms": "2", "bathrooms": "2", "area_sqft": "1000",
        "furnishing": "Furnished", "availability": "Available",
        "amenities": ["Parking", "Lift", "NotAnAmenity"], "image_url": ""})
    assert response.status_code == 302
    prop = db.properties.find_one({"title": "Brand New Flat"})
    assert prop["status"] == "pending"                      # needs admin approval
    assert prop["amenities"] == ["Parking", "Lift"]          # fake amenity dropped


def test_owner_property_validation_rejects_bad_data(client, db):
    make_user(db, "owner", email="o@test.example")
    login(client, "o@test.example")
    response = client.post("/owner/property/add", data={
        "title": "x", "description": "short", "location": "", "rent": "-5",
        "property_type": "Castle", "bedrooms": "abc", "bathrooms": "1",
        "area_sqft": "1000", "furnishing": "Furnished", "availability": "Available",
        "image_url": "javascript:alert(1)"})
    assert response.status_code == 200
    assert db.properties.count_documents({}) == 0


# ====================================================== property listing
def test_listing_shows_only_approved_properties(client, db):
    owner = make_user(db, "owner")
    make_property(db, owner, title="Visible Flat", status="approved")
    make_property(db, owner, title="Hidden Pending Flat", status="pending")
    make_property(db, owner, title="Hidden Rejected Flat", status="rejected")
    response = client.get("/properties")
    assert response.status_code == 200
    assert b"Visible Flat" in response.data
    assert b"Hidden Pending Flat" not in response.data
    assert b"Hidden Rejected Flat" not in response.data


def test_listing_filter_by_max_rent(client, db):
    owner = make_user(db, "owner")
    make_property(db, owner, title="Cheap Flat Alpha", rent=10000)
    make_property(db, owner, title="Pricey Flat Beta", rent=50000)
    response = client.get("/properties?max_rent=20000")
    assert b"Cheap Flat Alpha" in response.data
    assert b"Pricey Flat Beta" not in response.data


def test_listing_filter_by_min_rent(client, db):
    owner = make_user(db, "owner")
    make_property(db, owner, title="Cheap Flat Alpha", rent=10000)
    make_property(db, owner, title="Pricey Flat Beta", rent=50000)
    response = client.get("/properties?min_rent=30000")
    assert b"Pricey Flat Beta" in response.data
    assert b"Cheap Flat Alpha" not in response.data


def test_listing_filter_by_location_type_and_bedrooms(client, db):
    owner = make_user(db, "owner")
    make_property(db, owner, title="Chennai Apartment One", location="Velachery, Chennai",
                  property_type="Apartment", bedrooms=2)
    make_property(db, owner, title="Pune Villa Two", location="Baner, Pune",
                  property_type="Villa", bedrooms=4)

    assert b"Chennai Apartment One" in client.get("/properties?location=chennai").data
    assert b"Pune Villa Two" not in client.get("/properties?location=chennai").data
    assert b"Pune Villa Two" in client.get("/properties?property_type=Villa").data
    assert b"Chennai Apartment One" not in client.get("/properties?property_type=Villa").data
    assert b"Pune Villa Two" in client.get("/properties?bedrooms=3").data
    assert b"Chennai Apartment One" not in client.get("/properties?bedrooms=3").data


def test_listing_sorting_by_rent(client, db):
    owner = make_user(db, "owner")
    make_property(db, owner, title="Cheap Flat Alpha", rent=10000)
    make_property(db, owner, title="Pricey Flat Beta", rent=50000)

    low = client.get("/properties?sort=low").data.decode()
    assert low.index("Cheap Flat Alpha") < low.index("Pricey Flat Beta")
    high = client.get("/properties?sort=high").data.decode()
    assert high.index("Pricey Flat Beta") < high.index("Cheap Flat Alpha")


def test_listing_shows_message_when_nothing_matches(client, db):
    owner = make_user(db, "owner")
    make_property(db, owner, title="Cheap Flat Alpha", rent=10000)
    response = client.get("/properties?location=Atlantis")
    assert response.status_code == 200
    assert b"No properties match your filters" in response.data


def test_listing_survives_weird_filter_input(client, db):
    response = client.get("/properties?location=((&min_rent=abc&max_rent=&bedrooms=x&sort=zzz")
    assert response.status_code == 200


# ======================================================= property details
def test_property_detail_page_loads(client, db):
    owner = make_user(db, "owner")
    pid = make_property(db, owner, title="Detail Test Flat")
    response = client.get(f"/property/{pid}")
    assert response.status_code == 200
    assert b"Detail Test Flat" in response.data


def test_invalid_property_id_gives_404(client):
    response = client.get("/property/not-a-valid-id")
    assert response.status_code == 404
    assert b"Page Not Found" in response.data


def test_missing_property_id_gives_404(client):
    assert client.get(f"/property/{MISSING_ID}").status_code == 404


def test_pending_property_hidden_from_public_but_visible_to_owner(client, db):
    owner = make_user(db, "owner", email="o@test.example")
    pid = make_property(db, owner, status="pending")
    assert client.get(f"/property/{pid}").status_code == 404

    login(client, "o@test.example")
    assert client.get(f"/property/{pid}").status_code == 200


def test_unknown_url_gives_404_page(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert b"Page Not Found" in response.data


# ============================================================== wishlist
def test_wishlist_toggle_saves_and_removes_in_database(client, db):
    owner = make_user(db, "owner")
    tenant = make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner)
    login(client, "t@test.example")
    headers = {"X-Requested-With": "fetch"}

    first = client.post(f"/wishlist/toggle/{pid}", headers=headers)
    assert first.get_json()["wishlisted"] is True
    assert db.wishlists.count_documents({"user_id": tenant, "property_id": pid}) == 1

    second = client.post(f"/wishlist/toggle/{pid}", headers=headers)
    assert second.get_json()["wishlisted"] is False
    assert db.wishlists.count_documents({}) == 0


def test_wishlist_rejects_invalid_property(client, db):
    make_user(db, "tenant", email="t@test.example")
    login(client, "t@test.example")
    response = client.post("/wishlist/toggle/not-an-id", headers={"X-Requested-With": "fetch"})
    assert response.status_code == 404


def test_wishlist_page_lists_saved_property(client, db):
    owner = make_user(db, "owner")
    tenant = make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner, title="Saved Flat Gamma")
    db.wishlists.insert_one({"user_id": tenant, "property_id": pid, "created_at": models.utcnow()})
    login(client, "t@test.example")
    assert b"Saved Flat Gamma" in client.get("/wishlist").data


# ============================================================== enquiries
def test_tenant_can_send_enquiry(client, db):
    owner = make_user(db, "owner")
    tenant = make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner)
    login(client, "t@test.example")

    response = client.post(f"/enquiry/{pid}", data={"message": "Hello, is this still available?"})
    assert response.status_code == 302
    enquiry = db.enquiries.find_one({})
    assert enquiry["tenant_id"] == tenant
    assert enquiry["owner_id"] == owner
    assert enquiry["status"] == "Pending"


def test_short_enquiry_is_rejected(client, db):
    owner = make_user(db, "owner")
    make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner)
    login(client, "t@test.example")
    client.post(f"/enquiry/{pid}", data={"message": "hi"})
    assert db.enquiries.count_documents({}) == 0


def test_enquiry_blocked_for_rented_property(client, db):
    owner = make_user(db, "owner")
    make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner, availability="Rented")
    login(client, "t@test.example")
    client.post(f"/enquiry/{pid}", data={"message": "Hello, is this still available?"})
    assert db.enquiries.count_documents({}) == 0


def test_owner_cannot_send_enquiry(client, db):
    owner = make_user(db, "owner", email="o@test.example")
    pid = make_property(db, owner)
    login(client, "o@test.example")
    assert client.post(f"/enquiry/{pid}", data={"message": "Hello there, testing."}).status_code == 403


def test_tenants_only_see_their_own_enquiries(client, db):
    owner = make_user(db, "owner")
    tenant1 = make_user(db, "tenant", email="t1@test.example")
    make_user(db, "tenant", email="t2@test.example")
    pid = make_property(db, owner)
    db.enquiries.insert_one(models.build_enquiry_doc(tenant1, owner, pid, "UNIQUE-SECRET-MESSAGE-123"))

    login(client, "t1@test.example")
    assert b"UNIQUE-SECRET-MESSAGE-123" in client.get("/enquiries").data

    client.post("/logout")
    login(client, "t2@test.example")
    assert b"UNIQUE-SECRET-MESSAGE-123" not in client.get("/enquiries").data


def test_owners_only_see_enquiries_for_their_properties(client, db):
    owner1 = make_user(db, "owner", email="o1@test.example")
    make_user(db, "owner", email="o2@test.example")
    tenant = make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner1)
    db.enquiries.insert_one(models.build_enquiry_doc(tenant, owner1, pid, "UNIQUE-OWNER1-MESSAGE-456"))

    login(client, "o1@test.example")
    assert b"UNIQUE-OWNER1-MESSAGE-456" in client.get("/owner/enquiries").data

    client.post("/logout")
    login(client, "o2@test.example")
    assert b"UNIQUE-OWNER1-MESSAGE-456" not in client.get("/owner/enquiries").data


def test_owner_can_update_enquiry_status(client, db):
    owner = make_user(db, "owner", email="o@test.example")
    tenant = make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner)
    eid = db.enquiries.insert_one(
        models.build_enquiry_doc(tenant, owner, pid, "Hello, is this available?")).inserted_id

    login(client, "o@test.example")
    client.post(f"/owner/enquiries/{eid}/status", data={"status": "Contacted"})
    assert db.enquiries.find_one({"_id": eid})["status"] == "Contacted"

    # an invalid status value is refused
    assert client.post(f"/owner/enquiries/{eid}/status", data={"status": "Hacked"}).status_code == 400
    assert db.enquiries.find_one({"_id": eid})["status"] == "Contacted"


def test_owner_cannot_update_another_owners_enquiry(client, db):
    owner1 = make_user(db, "owner", email="o1@test.example")
    make_user(db, "owner", email="o2@test.example")
    tenant = make_user(db, "tenant", email="t@test.example")
    pid = make_property(db, owner1)
    eid = db.enquiries.insert_one(
        models.build_enquiry_doc(tenant, owner1, pid, "Hello, is this available?")).inserted_id

    login(client, "o2@test.example")
    assert client.post(f"/owner/enquiries/{eid}/status", data={"status": "Closed"}).status_code == 404
    assert db.enquiries.find_one({"_id": eid})["status"] == "Pending"


# ================================================================== admin
def test_admin_can_approve_reject_and_remove(client, db):
    owner = make_user(db, "owner")
    make_user(db, "admin", email="a@test.example")
    pid = make_property(db, owner, status="pending")
    login(client, "a@test.example")

    client.post(f"/admin/property/{pid}/status", data={"action": "approve"})
    assert db.properties.find_one({"_id": pid})["status"] == "approved"

    client.post(f"/admin/property/{pid}/status", data={"action": "reject"})
    assert db.properties.find_one({"_id": pid})["status"] == "rejected"

    client.post(f"/admin/property/{pid}/status", data={"action": "remove"})
    assert db.properties.count_documents({"_id": pid}) == 0


def test_admin_invalid_action_is_refused(client, db):
    owner = make_user(db, "owner")
    make_user(db, "admin", email="a@test.example")
    pid = make_property(db, owner, status="pending")
    login(client, "a@test.example")
    assert client.post(f"/admin/property/{pid}/status", data={"action": "explode"}).status_code == 400


def test_admin_dashboard_shows_counts_and_users_page(client, db):
    make_user(db, "tenant", email="t@test.example")
    make_user(db, "owner", email="o@test.example")
    make_user(db, "admin", email="a@test.example")
    login(client, "a@test.example")
    assert client.get("/admin/dashboard").status_code == 200
    users_page = client.get("/admin/users")
    assert users_page.status_code == 200
    assert b"t@test.example" in users_page.data


# ================================================================= profile
def test_profile_update(client, db):
    make_user(db, "tenant", email="t@test.example")
    login(client, "t@test.example")
    response = client.post("/profile", data={"name": "New Name", "phone": "9123456789"})
    assert response.status_code == 302
    user = db.users.find_one({"email": "t@test.example"})
    assert user["name"] == "New Name"
    assert user["phone"] == "9123456789"


# ============================================================ CSRF check
def test_post_without_csrf_token_is_rejected():
    """With CSRF protection ON, a POST with no token must be refused."""
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    try:
        response = flask_app.test_client().post("/login", data={"email": "a@b.co", "password": "x"})
        assert response.status_code == 400
        assert b"Session Expired" in response.data
    finally:
        flask_app.config.update(WTF_CSRF_ENABLED=False)