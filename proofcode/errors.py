class ProofCodeError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(ProofCodeError):
    pass


class ModelError(ProofCodeError):
    pass


class ProtocolError(ProofCodeError):
    pass


class ToolError(ProofCodeError):
    pass


class PathViolation(ToolError):
    pass


class ApprovalDenied(ToolError):
    pass
