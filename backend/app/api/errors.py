"""Public errors contain fixed messages and safe field paths only."""

MESSAGES = {
    **{
        code: "请求无法完成，请查看咨询状态。"
        for code in (
            "VERSION_CONFLICT",
            "STATE_CONFLICT",
            "BUSY",
            "IDEMPOTENCY_CONFLICT",
            "SOURCE_NOT_FOUND",
            "SOURCE_TIMEOUT",
            "SOURCE_UNAVAILABLE",
            "SOURCE_INVALID_RESPONSE",
            "SOURCE_BINDING_MISMATCH",
            "SOURCE_REJECTED",
            "SOURCE_CONFLICT",
            "AUTHORIZATION_CHANGED",
            "BINDING_CHANGED",
            "OPERATION_INTERRUPTED",
        )
    },
    "AUTHENTICATION_FAILED": "用户名或密码无效。",
    "UNAUTHENTICATED": "请重新登录。",
    "FORBIDDEN": "无权访问此咨询。",
    "INVALID_REQUEST": "请求格式无效。",
    "ORDER_REFERENCE_MISSING": "此咨询没有订单绑定。",
    "CONTEXT_REQUIRED": "请先取得有效的当前 Context。",
    "RESOURCE_NOT_FOUND": "资源不存在。",
    "INTERNAL_ERROR": "请求无法完成，请凭请求 ID 联系支持。",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, details: dict | None = None):
        self.status = status
        self.code = code
        self.details = details or {}
        super().__init__(code)

    def payload(self, request_id: str) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": MESSAGES[self.code],
                "request_id": request_id,
                "details": self.details,
            }
        }
