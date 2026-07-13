class AssistantError(Exception):
    """Raised for validation/lookup failures in the assistant module, which uses the
    {"success": false, "error": {"code": ..., "message": ...}} contract (matching the
    newer analysis endpoints — data_summary/health_summary — rather than the older
    {"success": false, "message": ..., "data": None} shape)."""

    def __init__(self, status_code: int, message: str, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
