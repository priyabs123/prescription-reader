class AppError(Exception):
    """An error whose message is safe to show to the user.

    The API turns it into: {"error": {"code": "...", "message": "..."}}
    """

    status_code = 400
    code = "error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
