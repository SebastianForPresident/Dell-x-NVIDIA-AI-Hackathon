"""MongoDB access only; no UI, GIS, or model dependencies."""

import os
from datetime import datetime, timezone

from pymongo import MongoClient


def utcnow():
    return datetime.now(timezone.utc)


class MongoStore:
    def __init__(self, database):
        self.db = database

    @classmethod
    def from_env(cls):
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise ValueError("Set MONGODB_URI to enable persistence.")
        client = MongoClient(uri, serverSelectionTimeoutMS=3000, timeoutMS=5000,
                             tz_aware=True)
        try:
            client.admin.command("ping")
            store = cls(client[os.environ.get("MONGODB_DATABASE", "crop_forensics")])
            store.ensure_indexes()
            return store
        except Exception:
            client.close()
            raise

    def ensure_indexes(self):
        # Every collection also has MongoDB's unique _id index.
        self.db.investigations.create_index([("claim_id", 1), ("created_at", -1)])
        for name in ("evidence", "agent_actions", "follow_up_tasks", "reports"):
            self.db[name].create_index("investigation_id")
        self.db.follow_up_tasks.create_index([("investigation_id", 1), ("status", 1)])

    def insert_once(self, collection, document):
        self.db[collection].update_one({"_id": document["_id"]},
                                      {"$setOnInsert": document}, upsert=True)

    def get(self, collection, key):
        return self.db[collection].find_one({"_id": key})

    def related(self, collection, investigation_id):
        return list(self.db[collection].find({"investigation_id": investigation_id})
                    .sort([("created_at", 1), ("_id", 1)]))

    def list_investigations(self, limit=50):
        return list(self.db.investigations.find({}, {"context": 0})
                    .sort("created_at", -1).limit(limit))
