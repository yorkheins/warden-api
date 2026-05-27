from uuid import UUID


class WardenBaseError(Exception):
    pass


class LLMUnavailableError(WardenBaseError):
    pass


class LLMResponseMalformedError(WardenBaseError):
    pass


class EventNotFoundError(WardenBaseError):
    pass


class ApprovalNotFoundError(WardenBaseError):
    pass


class ApprovalAlreadyResolvedError(WardenBaseError):
    pass


class DuplicateEventError(WardenBaseError):
    def __init__(self, event_id: UUID) -> None:
        self.event_id = event_id
        super().__init__(f"Duplicate event: {event_id}")
