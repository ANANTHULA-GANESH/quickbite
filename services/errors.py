"""Exception types shared by the services. Messages are safe to show to users."""


class ValidationError(ValueError):
    """User input is invalid (HTTP 400)."""


class NotFoundError(LookupError):
    """The requested order or item does not exist (HTTP 404)."""


class ConflictError(RuntimeError):
    """The order changed since it was loaded (HTTP 409)."""


class DuplicateOrderError(RuntimeError):
    """An order ID collided with an existing order. Handled internally by retrying."""


class DuplicateItemError(RuntimeError):
    """A menu item ID collided with an existing item."""


class DuplicateStudentError(ConflictError):
    """A student account conflicts with an existing phone number or college ID."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
