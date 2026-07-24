class HealthReportError(Exception):
    """Raised for validation/lookup/ownership failures in the health_report module, which uses
    the {"success": false, "error": {"code": ..., "message": ...}} contract (same convention as
    src/assistant/services/errors.py::AssistantError)."""

    def __init__(self, status_code: int, message: str, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
