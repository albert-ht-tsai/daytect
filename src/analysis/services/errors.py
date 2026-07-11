class AnalysisError(Exception):
    """Raised for validation/lookup failures that map to the module's
    {"success": false, "message": ..., "data": null} error contract.

    `code` is optional and only populated by callers that need the
    {"success": false, "error": {"code": ..., "message": ...}} contract instead
    (see data_summary_service) — existing callers that omit it are unaffected.
    """

    def __init__(self, status_code: int, message: str, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
