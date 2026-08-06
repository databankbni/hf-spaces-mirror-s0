from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["smart_resolve_db"]

db.customeracc.update_many(
    {},
    {"$set": {"role": "customer"}}
)

db.adminlogin.update_many(
    {},
    {"$set": {"role": "admin"}}
)

db.branchmanager.update_many(
    {},
    {"$set": {"role": "branch_manager"}}
)

print("Updated!")