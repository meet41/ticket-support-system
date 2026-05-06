class WSEvent:
    TICKET_CREATED = "ticket_created"          # Notify all online engineers
    TICKET_TAKEN = "ticket_taken"              # Notify customer that engineer joined
    TICKET_RESOLVED = "ticket_resolved"        # Notify customer ticket is resolved
    TICKET_CLOSED = "ticket_closed"            # Notify customer ticket is closed
    TICKET_REOPENED = "ticket_reopened"        # Notify assigned engineer ticket reopened
