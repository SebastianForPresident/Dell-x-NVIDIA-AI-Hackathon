"""MongoDB connection and intentionally synthetic demo seeding."""

import os

from pymongo import MongoClient

from server.seed import demo_cases


MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MONGO_DB", "crop_forensics")
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
database = client[MONGO_DB]
cases = database["cases"]


def initialize_database() -> None:
    client.admin.command("ping")
    cases.create_index("id", unique=True)
    cases.create_index("created_at")
    cases.create_index("synthetic_demo")
    if cases.count_documents({}) == 0:
        cases.insert_many(demo_cases())


def case_document(case_id: str):
    return cases.find_one({"id": case_id}, {"_id": 0})
