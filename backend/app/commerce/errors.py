"""Closed commerce errors contain only deliberately disclosed safe fields."""

AI_MESSAGES = {
    "AI_UNAVAILABLE": "AI服务暂不可用，请联系平台管理员。",
    "AI_EMPTY_CONVERSATION": "会话尚无消息，发送消息后再生成摘要。",
    "AI_INPUT_LIMIT": "会话超过本次处理范围，暂无法完整生成摘要。",
    "AI_BUSY": "此会话正在生成摘要，请稍后刷新。",
    "AI_RATE_LIMITED": "生成请求较频繁，请稍后重试。",
    "AI_TIMEOUT": "AI服务响应超时，可重新尝试。",
    "AI_AUTH_FAILED": "AI服务认证失败，请联系平台管理员。",
    "AI_BALANCE_REQUIRED": "AI服务余额不足，请联系平台管理员。",
    "AI_PROVIDER_FAILED": "AI服务暂时失败，可稍后尝试。",
    "AI_INVALID_RESPONSE": "AI输出未通过校验，可重新尝试。",
    "AI_INTERRUPTED": "上次生成被中断，可重新尝试。",
}


class CommerceError(Exception):
    def __init__(self, status, code, details=None):
        self.status = status
        self.code = code
        self.details = details or {}

    def payload(self, request_id):
        return {
            "error": {
                "code": self.code,
                "message": AI_MESSAGES.get(self.code, self.code),
                "request_id": request_id,
                "details": self.details,
            }
        }


def fail(code, status=409, **details):
    raise CommerceError(status, code, details)
