class AnalysisError(Exception):
    """Raised for validation/lookup failures that map to the module's
    {"success": false, "message": ..., "data": null} error contract."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
