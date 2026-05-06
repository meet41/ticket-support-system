from motor.motor_asyncio import AsyncIOMotorClient

from app.config.settings import settings

_client: AsyncIOMotorClient = None
_db = None


async def connect_to_mongo():
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    _db = _client[settings.DATABASE_NAME]


async def close_mongo_connection():
    global _client
    if _client:
        _client.close()


def get_database():
    return _db