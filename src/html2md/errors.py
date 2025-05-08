"""Custom exceptions for html2md module."""


class Html2MdError(Exception):
    """Base class for all html2md-specific exceptions."""

    pass


class ConfigFileNotFoundError(Html2MdError):
    """Raised when the configuration file is missing or inaccessible."""

    pass


class ConfigurationLoadError(Html2MdError):
    """Raised when the configuration file cannot be parsed correctly."""

    pass


class InvalidModificationError(Html2MdError):
    """Raised when an invalid modification attempt is detected."""

    pass


class DecryptionError(Html2MdError):
    """Raised when cookie decryption fails."""

    pass
