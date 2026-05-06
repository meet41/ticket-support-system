import asyncio

# Single shared queue consumed by the notification broadcaster.
# Produces notification events when tickets are created, taken, resolved, closed, or reopened.
notification_queue: asyncio.Queue[dict] = asyncio.Queue()
