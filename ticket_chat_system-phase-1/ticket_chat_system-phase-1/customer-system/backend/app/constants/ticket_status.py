class TicketStatus:
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Predefined subjects shown to customer as dropdown
# Each subject has a priority auto-assigned in backend
SUBJECT_PRIORITY_MAP = {
    "Cannot login to my account":           TicketPriority.HIGH,
    "Password reset not working":           TicketPriority.HIGH,
    "Payment failed but amount deducted":   TicketPriority.HIGH,
    "App crashing on launch":               TicketPriority.HIGH,
    "Unable to access my data":             TicketPriority.HIGH,
    "Feature not working as expected":      TicketPriority.MEDIUM,
    "Slow performance / lagging":           TicketPriority.MEDIUM,
    "Notification not received":            TicketPriority.MEDIUM,
    "Profile update not saving":            TicketPriority.MEDIUM,
    "Integration issue with third-party":   TicketPriority.MEDIUM,
    "UI bug / display issue":               TicketPriority.LOW,
    "General query about product":          TicketPriority.LOW,
    "Request for new feature":              TicketPriority.LOW,
    "Billing inquiry":                      TicketPriority.LOW,
    "Other":                                TicketPriority.HIGH,
}

# List of subjects to send to frontend for dropdown
PREDEFINED_SUBJECTS = list(SUBJECT_PRIORITY_MAP.keys())
