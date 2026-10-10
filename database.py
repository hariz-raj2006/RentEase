"""MongoDB connection helpers (PyMongo)."""
from pymongo import MongoClient

from config import Config

_client = None
_db = None


def init_db(client=None, db_name=None):
    """Connect to MongoDB.

    Normally called with no arguments. Tests pass a fake client (mongomock)
    so that your real Atlas database is never touched.
    """
    global _client, _db
    if client is not None:
        _client = client
    else:
        _client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
    _db = _client[db_name or Config.DB_NAME]
    return _db


def get_db():
    """Return the database object, connecting the first time it is needed."""
    if _db is None:
        init_db()
    return _db


def ensure_indexes():
    """Create indexes. Safe to run many times."""
    db = get_db()

    # Two users can never share an email address
    db.users.create_index("email", unique=True)

    # Faster lookups for the pages we show
    db.properties.create_index("owner_id")
    db.properties.create_index([("status", 1), ("created_at", -1)])
    db.properties.create_index("rent")

    # A user can save a given property only once
    db.wishlists.create_index([("user_id", 1), ("property_id", 1)], unique=True)

    db.enquiries.create_index("tenant_id")
    db.enquiries.create_index("owner_id")
    db.enquiries.create_index("property_id")