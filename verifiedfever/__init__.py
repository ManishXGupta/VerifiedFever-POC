"""VerifiedFever: proof of concept for device-verified fever readings and
automated, clinician-validated digital absence certificates for schools."""

from .device import VirtualThermometer
from .rules import Decision, Policy, evaluate, personal_baseline
from .service import FeverCertService
from .verifier import Verdict

__all__ = ["VirtualThermometer", "Decision", "Policy", "evaluate", "personal_baseline",
           "FeverCertService", "Verdict"]
__version__ = "0.1.0"
