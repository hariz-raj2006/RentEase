"""RentEase - main Flask application (routes + helper functions)."""
import re
from functools import wraps
from urllib.parse import urlparse

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_wtf.csrf import CSRFError, CSRFProtect
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.security import check_password_hash

import models
from config import Config
from database import ensure_indexes, get_db

app = Flask(__name__)
app.config.from_object(Config)
csrf = CSRFProtect(app)      # every POST must carry a valid CSRF token


# ====================================================================
# Helper functions
# ====================================================================
def get_current_user():
    """Return the logged-in user (as a dict) or None. Cached per request."""
    if not hasattr(g, "current_user"):
        g.current_user = None
        user_id = models.parse_object_id(session.get("user_id"))
        if user_id:
            try:
                user = get_db().users.find_one({"_id": user_id})
            except PyMongoError:
                user = None
            if user:
                g.current_user = models.serialize(user)
    return g.current_user


def wants_json():
    """True when the request came from our JavaScript fetch() calls."""
    return request.headers.get("X-Requested-With") == "fetch"


def role_required(*roles):
    """Allow only logged-in users. If roles are given, the user must have one."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if user is None:
                if wants_json():
                    return jsonify(ok=False, message="Please log in first.",
                                   login_url=url_for("login")), 401
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login", next=request.path))
            if roles and user["role"] not in roles:
                if wants_json():
                    return jsonify(ok=False, message="You do not have permission."), 403
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def login_required(view):
    return role_required()(view)


def is_safe_next(target):
    """Only allow redirects to pages inside our own site."""
    return bool(target) and target.startswith("/") and not target.startswith("//") \
        and "\\" not in target


def redirect_back(default_endpoint):
    """Go back to the page the user came from (if it is our own site)."""
    ref = request.referrer
    if ref and urlparse(ref).netloc == request.host:
        return redirect(ref)
    return redirect(url_for(default_endpoint))


def get_wishlist_ids(user):
    """Set of property id strings that this tenant has saved."""
    if user and user["role"] == "tenant":
        rows = get_db().wishlists.find({"user_id": user["_id"]})
        return {str(row["property_id"]) for row in rows}
    return set()


def fetch_properties_by_ids(ids, only_approved=True):
    """Fetch properties for a list of ids, keeping the same order."""
    if not ids:
        return []
    query = {"_id": {"$in": list(ids)}}
    if only_approved:
        query["status"] = "approved"
    found = {p["_id"]: models.serialize(p) for p in get_db().properties.find(query)}
    return [found[i] for i in ids if i in found]


def attach_properties(enquiries):
    """Add e['property'] (title, id, ...) to each enquiry."""
    ids = list({e["property_id"] for e in enquiries})
    props = {}
    if ids:
        props = {p["_id"]: models.serialize(p)
                 for p in get_db().properties.find({"_id": {"$in": ids}})}
    for e in enquiries:
        e["property"] = props.get(e["property_id"])
    return enquiries


def attach_users(rows, id_field, target_key):
    """Add row[target_key] = {name, email, phone} by looking up row[id_field]."""
    ids = list({r[id_field] for r in rows})
    people = {}
    if ids:
        people = {u["_id"]: u for u in get_db().users.find(
            {"_id": {"$in": ids}}, {"name": 1, "email": 1, "phone": 1})}
    for r in rows:
        r[target_key] = people.get(r[id_field])
    return rows


def delete_property_and_related(property_id):
    """Delete a property together with its wishlist entries and enquiries."""
    db = get_db()
    db.properties.delete_one({"_id": property_id})
    db.wishlists.delete_many({"property_id": property_id})
    db.enquiries.delete_many({"property_id": property_id})


def get_owned_property_or_404(property_id):
    """Return the property only if the logged-in owner owns it. Otherwise 404."""
    user = get_current_user()
    pid = models.parse_object_id(property_id)
    prop = None
    if pid:
        prop = get_db().properties.find_one({"_id": pid, "owner_id": user["_id"]})
    if not prop:
        abort(404)
    return prop


# ====================================================================
# Template filters and globals
# ====================================================================
@app.template_filter("rupees")
def rupees_filter(value):
    try:
        return "₹{:,}".format(int(value))
    except (TypeError, ValueError):
        return "₹0"


@app.template_filter("date")
def date_filter(value):
    return value.strftime("%d %b %Y") if value else ""


@app.context_processor
def inject_globals():
    """Variables available in EVERY template."""
    return {
        "current_user": get_current_user(),
        "PROPERTY_TYPES": models.PROPERTY_TYPES,
        "FURNISHING_OPTIONS": models.FURNISHING_OPTIONS,
        "AVAILABILITY_OPTIONS": models.AVAILABILITY_OPTIONS,
        "AMENITY_OPTIONS": models.AMENITY_OPTIONS,
        "ENQUIRY_STATUSES": models.ENQUIRY_STATUSES,
        "SAMPLE_IMAGES": models.SAMPLE_IMAGES,
    }


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# ====================================================================
# Public pages
# ====================================================================
@app.route("/")
def index():
    db = get_db()
    user = get_current_user()
    approved = {"status": "approved"}

    featured = models.serialize_list(
        db.properties.find(approved).sort("created_at", -1).limit(6))
    type_counts = {t: db.properties.count_documents({**approved, "property_type": t})
                   for t in models.PROPERTY_TYPES}
    stats = {
        "properties": db.properties.count_documents(approved),
        "tenants": db.users.count_documents({"role": "tenant"}),
        "owners": db.users.count_documents({"role": "owner"}),
        "enquiries": db.enquiries.count_documents({}),
    }
    return render_template("index.html", featured=featured, type_counts=type_counts,
                           stats=stats, wishlist_ids=get_wishlist_ids(user))


@app.route("/properties")
def properties():
    db = get_db()
    user = get_current_user()

    filters = {
        "location": request.args.get("location", "").strip(),
        "property_type": request.args.get("property_type", "").strip(),
        "min_rent": request.args.get("min_rent", "").strip(),
        "max_rent": request.args.get("max_rent", "").strip(),
        "bedrooms": request.args.get("bedrooms", "").strip(),
        "sort": request.args.get("sort", "newest").strip(),
    }

    query = {"status": "approved"}          # visitors only see approved listings

    if filters["location"]:
        # re.escape makes sure typed characters are treated as plain text
        query["location"] = {"$regex": re.escape(filters["location"][:60]),
                             "$options": "i"}
    if filters["property_type"] in models.PROPERTY_TYPES:
        query["property_type"] = filters["property_type"]

    rent_range = {}
    min_rent = models.to_int(filters["min_rent"])
    max_rent = models.to_int(filters["max_rent"])
    if min_rent is not None and min_rent >= 0:
        rent_range["$gte"] = min_rent
    if max_rent is not None and max_rent >= 0:
        rent_range["$lte"] = max_rent
    if rent_range:
        query["rent"] = rent_range

    bedrooms = models.to_int(filters["bedrooms"])
    if bedrooms is not None and bedrooms > 0:
        query["bedrooms"] = {"$gte": bedrooms}      # "2+" means 2 or more

    sort_options = {
        "low": [("rent", 1)],
        "high": [("rent", -1)],
        "newest": [("created_at", -1)],
    }
    sort_spec = sort_options.get(filters["sort"], sort_options["newest"])

    results = models.serialize_list(db.properties.find(query).sort(sort_spec))
    return render_template("properties.html", results=results, filters=filters,
                           wishlist_ids=get_wishlist_ids(user))


@app.route("/property/<property_id>")
def property_detail(property_id):
    db = get_db()
    user = get_current_user()

    pid = models.parse_object_id(property_id)
    prop = db.properties.find_one({"_id": pid}) if pid else None
    if not prop:
        abort(404)

    # Unapproved listings are visible only to their owner and to admins
    is_owner = bool(user) and user["_id"] == prop["owner_id"]
    is_admin = bool(user) and user["role"] == "admin"
    if prop["status"] != "approved" and not (is_owner or is_admin):
        abort(404)

    owner = db.users.find_one({"_id": prop["owner_id"]},
                              {"name": 1, "email": 1, "phone": 1})
    in_wishlist = str(prop["_id"]) in get_wishlist_ids(user)
    can_enquire = (bool(user) and user["role"] == "tenant"
                   and prop["status"] == "approved"
                   and prop.get("availability") == "Available")

    return render_template("property_detail.html", prop=models.serialize(prop),
                           owner=owner, in_wishlist=in_wishlist,
                           can_enquire=can_enquire)


# ====================================================================
# Registration, login, logout
# ====================================================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if get_current_user():
        return redirect(url_for("dashboard"))

    form = {}
    if request.method == "POST":
        errors, cleaned = models.validate_registration(request.form)
        form = {k: request.form.get(k, "") for k in ("name", "email", "phone", "role")}

        if not errors:
            db = get_db()
            if db.users.find_one({"email": cleaned["email"]}):
                errors.append("An account with this email already exists.")
            else:
                try:
                    db.users.insert_one(models.build_user_doc(cleaned))
                except DuplicateKeyError:       # safety net from the unique index
                    errors.append("An account with this email already exists.")

        if not errors:
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))
        for message in errors:
            flash(message, "error")

    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard"))

    next_url = request.args.get("next", "")
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.", "error")
        else:
            user = get_db().users.find_one({"email": email})
            if user and check_password_hash(user["password_hash"], password):
                session.clear()                     # start a fresh session
                session["user_id"] = str(user["_id"])
                session.permanent = True
                flash(f"Welcome back, {user['name']}!", "success")
                if is_safe_next(next_url):
                    return redirect(next_url)
                return redirect(url_for("dashboard"))
            # Same message for wrong email OR wrong password (no hints for attackers)
            flash("Invalid email or password.", "error")

    return render_template("login.html", email=email, next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ====================================================================
# Dashboards (role based)
# ====================================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    if user["role"] == "owner":
        return redirect(url_for("owner_dashboard"))
    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))

    db = get_db()
    wish_rows = list(db.wishlists.find({"user_id": user["_id"]}).sort("created_at", -1))
    wishlist_properties = fetch_properties_by_ids([w["property_id"] for w in wish_rows][:3])

    enquiry_query = {"tenant_id": user["_id"]}
    recent = list(db.enquiries.find(enquiry_query).sort("created_at", -1).limit(5))
    recent = attach_properties(models.serialize_list(recent))

    return render_template(
        "tenant_dashboard.html",
        wishlist_properties=wishlist_properties,
        wishlist_count=len(wish_rows),
        enquiries=recent,
        enquiry_count=db.enquiries.count_documents(enquiry_query),
        pending_count=db.enquiries.count_documents({**enquiry_query, "status": "Pending"}),
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = get_current_user()
    if request.method == "POST":
        errors, cleaned = models.validate_profile(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            get_db().users.update_one(
                {"_id": user["_id"]},
                {"$set": {"name": cleaned["name"], "phone": cleaned["phone"]}})
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html")


# ====================================================================
# Tenant: wishlist and enquiries
# ====================================================================
@app.route("/wishlist")
@role_required("tenant")
def wishlist():
    user = get_current_user()
    rows = get_db().wishlists.find({"user_id": user["_id"]}).sort("created_at", -1)
    saved = fetch_properties_by_ids([w["property_id"] for w in rows])
    return render_template("wishlist.html", results=saved,
                           wishlist_ids={p["id"] for p in saved})


@app.route("/wishlist/toggle/<property_id>", methods=["POST"])
@role_required("tenant")
def wishlist_toggle(property_id):
    db = get_db()
    user = get_current_user()
    pid = models.parse_object_id(property_id)

    prop = db.properties.find_one({"_id": pid, "status": "approved"}) if pid else None
    if not prop:
        if wants_json():
            return jsonify(ok=False, message="Property not found."), 404
        abort(404)

    key = {"user_id": user["_id"], "property_id": pid}
    existing = db.wishlists.find_one(key)
    if existing:
        db.wishlists.delete_one({"_id": existing["_id"]})
        wishlisted, message = False, "Removed from your wishlist."
    else:
        try:
            db.wishlists.insert_one({**key, "created_at": models.utcnow()})
        except DuplicateKeyError:
            pass
        wishlisted, message = True, "Saved to your wishlist."

    if wants_json():
        return jsonify(ok=True, wishlisted=wishlisted, message=message)
    flash(message, "success")
    return redirect_back("properties")


@app.route("/enquiry/<property_id>", methods=["POST"])
@role_required("tenant")
def send_enquiry(property_id):
    db = get_db()
    user = get_current_user()
    pid = models.parse_object_id(property_id)

    prop = db.properties.find_one({"_id": pid, "status": "approved"}) if pid else None
    if not prop:
        abort(404)

    if prop.get("availability") != "Available":
        flash("This property is no longer available.", "error")
        return redirect(url_for("property_detail", property_id=property_id))

    errors, message = models.validate_enquiry_message(request.form.get("message"))
    if errors:
        for err in errors:
            flash(err, "error")
        return redirect(url_for("property_detail", property_id=property_id))

    db.enquiries.insert_one(
        models.build_enquiry_doc(user["_id"], prop["owner_id"], pid, message))
    flash("Your enquiry has been sent to the owner.", "success")
    return redirect(url_for("enquiries"))


@app.route("/enquiries")
@role_required("tenant")
def enquiries():
    user = get_current_user()
    rows = get_db().enquiries.find({"tenant_id": user["_id"]}).sort("created_at", -1)
    return render_template("enquiries.html",
                           enquiries=attach_properties(models.serialize_list(rows)))


# ====================================================================
# Property owner
# ====================================================================
@app.route("/owner/dashboard")
@role_required("owner")
def owner_dashboard():
    db = get_db()
    user = get_current_user()

    props = models.serialize_list(
        db.properties.find({"owner_id": user["_id"]}).sort("created_at", -1))
    for p in props:
        p["enquiry_count"] = db.enquiries.count_documents({"property_id": p["_id"]})

    stats = {
        "total": len(props),
        "approved": sum(1 for p in props if p["status"] == "approved"),
        "pending": sum(1 for p in props if p["status"] == "pending"),
        "enquiries": db.enquiries.count_documents({"owner_id": user["_id"]}),
        "new_enquiries": db.enquiries.count_documents(
            {"owner_id": user["_id"], "status": "Pending"}),
    }
    return render_template("owner_dashboard.html", properties=props, stats=stats)


@app.route("/owner/property/add", methods=["GET", "POST"])
@role_required("owner")
def property_add():
    user = get_current_user()
    form = dict(models.PROPERTY_FORM_DEFAULTS)

    if request.method == "POST":
        errors, cleaned = models.validate_property(request.form)
        form = models.property_form_values(request.form)
        if not errors:
            get_db().properties.insert_one(models.build_property_doc(cleaned, user["_id"]))
            flash("Property submitted! It will appear publicly after admin approval.",
                  "success")
            return redirect(url_for("owner_dashboard"))
        for message in errors:
            flash(message, "error")

    return render_template("property_form.html", mode="add", form=form, prop=None)


@app.route("/owner/property/edit/<property_id>", methods=["GET", "POST"])
@role_required("owner")
def property_edit(property_id):
    prop = get_owned_property_or_404(property_id)
    form = dict(prop)

    if request.method == "POST":
        errors, cleaned = models.validate_property(request.form)
        form = models.property_form_values(request.form)
        if not errors:
            changes = dict(cleaned)
            changes["updated_at"] = models.utcnow()
            if prop["status"] == "rejected":
                changes["status"] = "pending"       # resubmit for review
            get_db().properties.update_one({"_id": prop["_id"]}, {"$set": changes})
            flash("Property updated.", "success")
            return redirect(url_for("owner_dashboard"))
        for message in errors:
            flash(message, "error")

    return render_template("property_form.html", mode="edit", form=form,
                           prop=models.serialize(prop))


@app.route("/owner/property/delete/<property_id>", methods=["POST"])
@role_required("owner")
def property_delete(property_id):
    prop = get_owned_property_or_404(property_id)
    delete_property_and_related(prop["_id"])
    flash("Property deleted.", "success")
    return redirect(url_for("owner_dashboard"))


@app.route("/owner/enquiries")
@role_required("owner")
def owner_enquiries():
    user = get_current_user()
    query = {"owner_id": user["_id"]}

    filter_pid = models.parse_object_id(request.args.get("property_id"))
    if filter_pid:
        query["property_id"] = filter_pid

    rows = models.serialize_list(
        get_db().enquiries.find(query).sort("created_at", -1))
    rows = attach_users(attach_properties(rows), "tenant_id", "tenant")
    return render_template("owner_enquiries.html", enquiries=rows,
                           filtered=bool(filter_pid))


@app.route("/owner/enquiries/<enquiry_id>/status", methods=["POST"])
@role_required("owner")
def owner_enquiry_status(enquiry_id):
    user = get_current_user()
    eid = models.parse_object_id(enquiry_id)
    new_status = request.form.get("status", "")

    if not eid or new_status not in models.ENQUIRY_STATUSES:
        abort(400)

    # The owner_id filter guarantees owners can only update THEIR enquiries
    result = get_db().enquiries.update_one(
        {"_id": eid, "owner_id": user["_id"]}, {"$set": {"status": new_status}})
    if result.matched_count == 0:
        abort(404)

    flash(f"Enquiry marked as {new_status}.", "success")
    return redirect_back("owner_enquiries")


# ====================================================================
# Administrator
# ====================================================================
@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    db = get_db()

    stats = {
        "users": db.users.count_documents({}),
        "properties": db.properties.count_documents({}),
        "tenants": db.users.count_documents({"role": "tenant"}),
        "owners": db.users.count_documents({"role": "owner"}),
        "enquiries": db.enquiries.count_documents({}),
        "pending": db.properties.count_documents({"status": "pending"}),
    }

    status_filter = request.args.get("status", "")
    query = {"status": status_filter} if status_filter in models.LISTING_STATUSES else {}
    props = models.serialize_list(db.properties.find(query).sort("created_at", -1))
    props = attach_users(props, "owner_id", "owner")

    recent_users = models.serialize_list(db.users.find().sort("created_at", -1).limit(5))
    return render_template("admin_dashboard.html", stats=stats, properties=props,
                           recent_users=recent_users, status_filter=status_filter)


@app.route("/admin/property/<property_id>/status", methods=["POST"])
@role_required("admin")
def admin_property_status(property_id):
    pid = models.parse_object_id(property_id)
    action = request.form.get("action", "")
    if not pid or action not in ("approve", "reject", "remove"):
        abort(400)

    db = get_db()
    if not db.properties.find_one({"_id": pid}):
        abort(404)

    if action == "approve":
        db.properties.update_one({"_id": pid}, {"$set": {"status": "approved"}})
        flash("Listing approved.", "success")
    elif action == "reject":
        db.properties.update_one({"_id": pid}, {"$set": {"status": "rejected"}})
        flash("Listing rejected.", "success")
    else:
        delete_property_and_related(pid)
        flash("Listing removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users")
@role_required("admin")
def admin_users():
    users = models.serialize_list(get_db().users.find().sort("created_at", -1))
    return render_template("admin_users.html", users=users)


# ====================================================================
# Error pages (never show database details or secrets)
# ====================================================================
ERROR_TEXT = {
    400: ("Bad Request", "Something was wrong with that request."),
    403: ("Access Denied", "You do not have permission to view this page."),
    404: ("Page Not Found", "We could not find what you were looking for."),
    405: ("Method Not Allowed", "That action is not allowed on this page."),
    413: ("Too Large", "The data you sent was too large."),
}


def make_error_handler(code):
    def handler(error):
        title, message = ERROR_TEXT[code]
        return render_template("error.html", code=code, title=title,
                               message=message), code
    return handler


for _code in ERROR_TEXT:
    app.register_error_handler(_code, make_error_handler(_code))


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_template(
        "error.html", code=400, title="Session Expired",
        message="Your form expired or was invalid. Please go back, refresh the page "
                "and try again."), 400


@app.errorhandler(PyMongoError)
def handle_database_error(error):
    app.logger.exception("Database error")      # details go to the terminal only
    return render_template(
        "error.html", code=500, title="Database Problem",
        message="We could not reach the database. Please try again in a moment."), 500


@app.errorhandler(500)
def handle_server_error(error):
    return render_template(
        "error.html", code=500, title="Server Error",
        message="Something went wrong on our side. Please try again."), 500


# ====================================================================
# Run the development server:  python app.py
# ====================================================================
if __name__ == "__main__":
    try:
        ensure_indexes()
    except PyMongoError as exc:
        print("\n[!] Could not connect to MongoDB. Check MONGO_URI in your .env file")
        print("    and your Atlas Network Access settings.")
        print(f"    Details: {type(exc).__name__}\n")
    app.run(debug=Config.DEBUG)