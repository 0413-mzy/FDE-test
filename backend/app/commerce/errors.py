"""Closed commerce errors contain only deliberately disclosed safe fields."""


class CommerceError(Exception):
    def __init__(self, status, code, details=None):
        self.status = status
        self.code = code
        self.details = details or {}

    def payload(self, request_id):
        return {
            "error": {
                "code": self.code,
                "message": self.code,
                "request_id": request_id,
                "details": self.details,
            }
        }


def fail(code, status=409, **details):
    raise CommerceError(status, code, details)
