"""Every way licensing can say no.

One exception type per thing a caller might reasonably do about it: a bad key
is the user's typo to fix, an offline activation is worth retrying later, and a
seat limit needs a different machine freed first.
"""

from __future__ import annotations


class LicenseError(Exception):
    """Base class for anything the licensing subsystem refuses."""

    #: Shown to the user as-is when nothing more specific is available.
    message = "The licence could not be verified."

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.message)


class InvalidKey(LicenseError):
    """The typed purchase key is malformed — wrong length, bad checksum."""

    message = "That licence key does not look right. Check it and try again."


class InvalidToken(LicenseError):
    """A stored licence file is corrupt, truncated, or signed by nobody."""

    message = "The stored licence file is damaged. Re-activate to repair it."


class SignatureInvalid(InvalidToken):
    """The signature does not match the payload or the issuing key."""

    message = "This licence was not issued by Jlang.dev."


class ActivationFailed(LicenseError):
    """The licence service answered, and the answer was no."""

    message = "Activation was refused."


class SeatLimitReached(ActivationFailed):
    """Every seat on the licence is already bound to another machine."""

    message = ("Every machine on this licence is in use. Deactivate one from "
               "its own copy of the app, or upgrade for more seats.")


class ServiceUnreachable(LicenseError):
    """The licence service could not be reached — worth retrying later."""

    message = ("Could not reach the licence service. Check your connection "
               "and try again.")


class TrialExhausted(LicenseError):
    """This machine has already had its trial."""

    message = "The 72-hour trial has already been used on this computer."


class ClockTampered(LicenseError):
    """The system clock moved backwards past a timestamp we already saw."""

    message = ("This computer's clock is set earlier than the last time the "
               "app ran. Fix the date and time, then restart.")
