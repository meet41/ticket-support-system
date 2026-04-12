# from ticket_chat_system.app.config.db import db


# async def generate_ticket_id() -> int:
#     """
#     Uses a MongoDB 'counters' collection to auto-increment ticket_id.
#     Thread-safe via findOneAndUpdate with atomic increment.
#     """
#     result = await db["counters"].find_one_and_update(
#         {"_id": "ticket_id"},
#         {"$inc": {"seq": 1}},
#         upsert=True,
#         return_document=True
#     )
#     return result["seq"]


# def generate_ticket_number(ticket_id: int) -> str:
#     """Formats ticket_id into readable ticket number e.g. TCK-5001"""
#     return f"TCK-{ticket_id}"


from app.config.db import tickets_collection
async def gen_ticket():
    last_ticket=await tickets_collection.find_one(
        {},
        sort=[("ticket_id",-1)]
    )
    next_id=1 if not last_ticket else last_ticket['ticket_id']+1
    ticket_number=f"TCK-{next_id}"
    return next_id,ticket_number