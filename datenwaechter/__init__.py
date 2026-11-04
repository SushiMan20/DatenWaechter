"""Datenwächter: erkennt sensible Daten, bevor sie in einen KI-Chat gelangen."""

from .detectors import Finding, scan_text
from .anonymize import Anonymizer

__all__ = ["Finding", "scan_text", "Anonymizer"]
__version__ = "0.2.0"
