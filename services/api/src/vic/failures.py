"""Typed run failures. The pipeline turns any RunFailure into `status=failed` + ErrorBody."""
from vic.contracts import ErrorBody


class RunFailure(Exception):
    code = "run_failed"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable

    def to_error_body(self) -> ErrorBody:
        return ErrorBody(code=self.code, message=self.message, retryable=self.retryable)


class ProviderError(RunFailure):          # timeouts, 429, 5xx: worth retrying
    code = "provider_error"
    retryable = True


class ProviderTimeout(ProviderError):
    code = "provider_timeout"


class ProviderAuthError(RunFailure):      # bad/missing key or unconfigured provider
    code = "provider_auth_error"


class MalformedModelOutput(RunFailure):
    code = "malformed_model_output"


class BudgetExceeded(RunFailure):
    code = "budget_exceeded"


class RunTimeout(RunFailure):
    code = "run_timeout"
    retryable = True


class SourceOutage(RunFailure):
    code = "source_outage"
    retryable = True


class ValidationFailed(RunFailure):
    code = "validation_failed"


class ModuleNotReady(RunFailure):         # a required R3/R4/R5 function is not available
    code = "module_not_ready"


class PromptNotFound(RunFailure):
    code = "prompt_not_found"