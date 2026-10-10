# RentEase: House and Property Rental Platform

A college project: a server-rendered rental website where **tenants** browse
properties, save favourites and send enquiries, **owners** list and manage
properties, and an **administrator** moderates listings.

> This is a learning project for local development and demonstration.
> It is **not** production-ready. See "Before deploying" below.

## Tech stack

HTML5 · CSS3 · vanilla JavaScript · Python Flask · MongoDB Atlas (PyMongo) ·
Jinja2 templates · Flask sessions · Werkzeug password hashing · Flask-WTF (CSRF)

## Features

- Home page with search, categories, featured listings and statistics
- Browse page with filters (location, type, min/max rent, bedrooms) and rent sorting
- Property detail pages with gallery, amenities, owner info and enquiry form
- Registration and login with hashed passwords (admin cannot self-register)
- Tenant: dashboard, wishlist (saved in MongoDB), enquiry tracking, profile
- Owner: add, edit, delete own properties; view enquiries; update enquiry status
- Admin: statistics, approve/reject/remove listings, list of users
- CSRF protection, role-based access, ownership checks, server-side validation

## Quick start (Windows PowerShell, inside the RentEase folder)

```powershell
py -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `SECRET_KEY` and `MONGO_URI` (your MongoDB Atlas connection string).

```powershell
py seed_data.py            # 12 live sample properties + 1 pending, 3 owners, 1 tenant
py seed_data.py --admin    # create your administrator account (asks for details)
py app.py                  # start the site
```

Open <http://127.0.0.1:5000> in your browser.

If PowerShell blocks activation, run this once and try again:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

## Sample accounts

Created by `py seed_data.py`. You choose the shared password when you run it.

| Role   | Email                              |
|--------|------------------------------------|
| Owner  | ananya.owner@rentease.example      |
| Owner  | rahul.owner@rentease.example       |
| Owner  | meera.owner@rentease.example       |
| Tenant | karthik.tenant@rentease.example    |
| Admin  | the email you enter with `--admin` |

## Run the tests

```powershell
py -m pytest -v
```

The tests use an in-memory fake database (mongomock). Your Atlas data is never touched.

## Project layout

```
app.py          routes and helper functions
config.py       settings read from .env
database.py     MongoDB connection and indexes
models.py       constants, validation, document builders
seed_data.py    sample data and admin creation
templates/      Jinja2 HTML pages (base.html is the shared layout)
static/         style.css, script.js, images/
tests/          automated tests
```

## Database collections

| Collection | Key fields |
|------------|-----------|
| users      | name, email (unique), phone, password_hash, role, created_at |
| properties | title, description, location, rent, property_type, bedrooms, bathrooms, area_sqft, furnishing, amenities, image_url, owner_id, status, availability, created_at |
| wishlists  | user_id, property_id, created_at (user + property pair is unique) |
| enquiries  | tenant_id, owner_id, property_id, message, status, created_at |

Collections are linked by `ObjectId` values: `properties.owner_id` points to a
user, and `wishlists` and `enquiries` point to users and properties.

## Before deploying anywhere public

- Set a long random `SECRET_KEY` and keep it private
- Set `FLASK_DEBUG=0`
- Serve over HTTPS and set `SESSION_COOKIE_SECURE=1`
- Run with a production server (for example Waitress or Gunicorn), not `py app.py`
- Restrict MongoDB Atlas network access to your server's IP address
- Add login rate limiting and email verification
- Never commit `.env` to Git

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Could not connect to MongoDB" | Check `MONGO_URI`, the database user's password, and Atlas Network Access |
| `ModuleNotFoundError` | Activate the virtual environment, then `pip install -r requirements.txt` |
| "Session Expired" on a form | Refresh the page and submit again |
| Port 5000 already in use | Close the other program, or change the port in `app.py` |
| Images missing | Normal when offline; a placeholder is shown |