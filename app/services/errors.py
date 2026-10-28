class NotFoundError(Exception):
    def __init__(self, resource: str, id: int):
        super().__init__(f"{resource} {id} not found")


class ConflictError(Exception):
    pass


class ReferenceNotFoundError(Exception):
    def __init__(self, missing: dict[str, str]):
        super().__init__("Referenced record not found")
        self.missing = missing


class RuleViolationError(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
