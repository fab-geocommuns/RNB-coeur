"""Type stubs for private_captcha library."""

from typing import Any

class VerificationResult:
    """Result of a captcha verification."""

    success: bool
    code: int

    def ok(self) -> bool: ...

class Client:
    """Private captcha client."""

    def __init__(self, api_key: str) -> None: ...
    def verify(self, solution: str, sitekey: str) -> VerificationResult: ...
