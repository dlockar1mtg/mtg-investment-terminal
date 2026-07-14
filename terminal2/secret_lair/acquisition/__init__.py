"""Secret Lair source acquisition and canonical catalog population."""
from .contracts import ACQUISITION_CONTRACTS, AcquisitionContract, get_acquisition_contract
from .engine import AcquisitionBuildResult, acquire_secret_lair_sources
from .exports import publish_secret_lair_acquisition
from .validation import AcquisitionValidationResult, validate_secret_lair_acquisition

__all__ = [
    "ACQUISITION_CONTRACTS", "AcquisitionBuildResult", "AcquisitionContract",
    "AcquisitionValidationResult", "acquire_secret_lair_sources",
    "get_acquisition_contract", "publish_secret_lair_acquisition",
    "validate_secret_lair_acquisition",
]
