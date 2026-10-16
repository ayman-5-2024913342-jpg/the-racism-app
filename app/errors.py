"""Application errors that map to structured JSON / HTML error responses.

JSON shape (kept compatible with the Milestone 2 front end, which reads ``detail``):
    {"detail": "<message>", "code": "<machine code>", ...extra}
"""
from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, **extra: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = extra

    def to_dict(self) -> dict:
        return {"detail": self.message, "code": self.code, **self.extra}
