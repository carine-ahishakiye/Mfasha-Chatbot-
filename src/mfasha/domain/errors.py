"""Exceptions raised by the MFASHA core. The API layer maps each one to an HTTP status."""


class MfashaError(Exception):
    """Base class for every error raised on purpose by MFASHA."""


class KnowledgeBaseError(MfashaError):
    """The knowledge base file is missing, empty or malformed."""


class InvalidAudioError(MfashaError):
    """The uploaded audio cannot be decoded or breaks a size/duration limit."""


class ServiceUnavailableError(MfashaError):
    """An optional component (speech-to-text, text-to-speech) is not installed or switched off."""
