from __future__ import annotations


class QuartzError(Exception):
    pass


class RegistrationError(QuartzError, ValueError):
    pass


class RegistrationRuntimeError(QuartzError, RuntimeError):
    pass


class MissingClassAttributeError(QuartzError, AttributeError):
    pass


class ClassValidationError(QuartzError, TypeError):
    pass


class PropertyTypeError(QuartzError, TypeError):
    pass


class PropertyValueError(QuartzError, ValueError):
    pass


class ReadOnlyError(QuartzError, AttributeError):
    pass


class RemovedStructError(QuartzError, ReferenceError):
    pass


class PollFailedError(QuartzError, RuntimeError):
    pass


class OperatorFailedError(QuartzError, RuntimeError):
    pass


class OperatorNotFoundError(QuartzError, AttributeError):
    pass


class ExecContextError(QuartzError, ValueError):
    pass


class LinkError(QuartzError, RuntimeError):
    pass


class RestrictedAccessError(QuartzError, AttributeError):
    pass


class NotImplementedInQuartz(QuartzError, NotImplementedError):

    symbol: str

    def __init__(self, symbol: str, detail: str = "") -> None:
        self.symbol = symbol
        msg = f"{symbol} is not implemented in Quartz"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class ManifestError(QuartzError, ValueError):

    problems: list[str]
    path: str

    def __init__(self, problems, path: str = "") -> None:
        self.problems = list(problems)
        self.path = path
        super().__init__("; ".join(self.problems))


class FileFormatError(QuartzError, ValueError):
    pass


class CompatError(QuartzError, RuntimeError):
    pass
