# This deliverable is considered developed content as defined in contract between BDF parties.


"""Detect potential errors in metadata values."""


class ErrorDetector:
    """Base class for error detection algorithms."""

    def detect_errors(self, df, field):
        """Detect potential errors in a field.

        To be implemented by specific detection algorithms.
        """
        raise NotImplementedError


class VocabularyValidator(ErrorDetector):
    """Detect errors by validating against controlled vocabularies."""

    pass


class PatternMatcher(ErrorDetector):
    """Detect errors using pattern matching."""

    pass


class MLDetector(ErrorDetector):
    """Detect errors using machine learning models."""

    pass


class ContextAnalyzer(ErrorDetector):
    """Detect errors by analyzing field context."""

    pass
