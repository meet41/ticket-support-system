import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt

MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "ticket_support_db"



def hash_password(plain_password: str) -> str:
    """Hash a plain text password using bcrypt."""
    # bcrypt works with bytes
    password_bytes = plain_password[:72].encode("utf-8")

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)

    return hashed.decode("utf-8")



async def seed():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]

    print("Starting database seed...")

    # ─────────────────────────────────────────────
    # 1. Roles
    # ─────────────────────────────────────────────
    roles = [
        {
            "role_id": 1,
            "role_name": "admin",
            "permissions": [
                "create_ticket",
                "view_all_tickets",
                "take_ticket",
                "send_message",
                "resolve_ticket",
                "close_ticket",
                "manage_users",
                "view_reports",
            ],
        },
        {
            "role_id": 2,
            "role_name": "support",
            "permissions": [
                "create_ticket",
                "view_all_tickets",
                "take_ticket",
                "send_message",
                "resolve_ticket",
            ],
        },
        {
            "role_id": 3,
            "role_name": "customer",
            "permissions": [
                "create_ticket",
                "view_own_tickets",
                "send_message",
            ],
        },
    ]

    for role in roles:
        existing = await db.roles.find_one({"role_id": role["role_id"]})
        if not existing:
            await db.roles.insert_one(role)
            print(f" Role inserted: {role['role_name']}")
        else:
            print(f" Role already exists: {role['role_name']}")

    # ─────────────────────────────────────────────
    # 2. Support Engineers & Admins
    # ─────────────────────────────────────────────
    staff_members = [
        {
            "support_id": 101,
            "name": "Arjun Mehta",
            "email": "arjun@company.com",
            "password": hash_password("Admin@123"),
            "role_id": 1,  # admin
            "department": "management",
            "team": "",   # admin sees all teams
            "is_active": True,
            "is_online": False,
            "last_seen": None,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "support_id": 102,
            "name": "Rahul Sharma",
            "email": "rahul@company.com",
            "password": hash_password("Support@123"),
            "role_id": 2,  # support
            "department": "technical",
            "team": "team1",
            "is_active": True,
            "is_online": False,
            "last_seen": None,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "support_id": 103,
            "name": "Priya Patel",
            "email": "priya@company.com",
            "password": hash_password("Support@123"),
            "role_id": 2,  # support
            "department": "billing",
            "team": "team2",
            "is_active": True,
            "is_online": False,
            "last_seen": None,
            "created_at": datetime.now(timezone.utc),
        },
    ]

    for staff in staff_members:
        existing = await db.support_engineers.find_one({"email": staff["email"]})
        if not existing:
            await db.support_engineers.insert_one(staff)
            print(f"Staff inserted: {staff['name']} ({staff['email']})")
        else:
            print(f"Staff already exists: {staff['email']}")

    # ─────────────────────────────────────────────
    # 3. Sample Customer (for testing)
    # ─────────────────────────────────────────────
    sample_customer = {
        "customer_id": 1,
        "name": "Bhavin Shah",
        "email": "bhavin@gmail.com",
        "password": hash_password("Customer@123"),
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    }

    existing = await db.customers.find_one({"email": sample_customer["email"]})
    if not existing:
        await db.customers.insert_one(sample_customer)
        print(f"Sample customer inserted: {sample_customer['email']}")
    else:
        print(f"Sample customer already exists: {sample_customer['email']}")

    # ─────────────────────────────────────────────
    # 4. Create indexes
    # ─────────────────────────────────────────────
    await db.customers.create_index("email", unique=True)
    await db.customers.create_index("customer_id", unique=True)
    await db.support_engineers.create_index("email", unique=True)
    await db.support_engineers.create_index("support_id", unique=True)
    await db.roles.create_index("role_id", unique=True)
    await db.roles.create_index("role_name", unique=True)
    await db.refresh_tokens.create_index("token", unique=True)
    await db.refresh_tokens.create_index("user_id")
    await db.refresh_tokens.create_index("expires_at")
    await db.tickets.create_index("ticket_id", unique=True)
    await db.tickets.create_index("ticket_number", unique=True)
    await db.tickets.create_index("customer_id")
    await db.tickets.create_index("status")
    print(" Indexes created.")

    client.close()
    print("\nSeed complete!")
    print("\nTest Credentials:")
    print("  Admin     → arjun@company.com    / Admin@123")
    print("  Support   → rahul@company.com    / Support@123")
    print("  Support   → priya@company.com    / Support@123")
    print("  Customer  → bhavin@gmail.com     / Customer@123")


if __name__ == "__main__":
    asyncio.run(seed())
