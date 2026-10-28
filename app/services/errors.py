class NotFoundError(Exception):
    def __init__(self, resource: str, id: int):
        super().__init__(f"{resource} {id} not found")


class ConflictError(Exception):
    pass
