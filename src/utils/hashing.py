import os
from src.utils.resource_path import resource_path

try:
    import pyprc
    _pyprc_available = True
except ImportError:
    pyprc = None
    _pyprc_available = False

_labels_loaded = False

def load_param_labels():
    """Load ParamLabels.csv for hash resolution. Call once at startup."""
    global _labels_loaded
    if _labels_loaded:
        return True
    if not _pyprc_available:
        return False

    labels_path = resource_path("ParamLabels.csv")
    if os.path.exists(labels_path):
        pyprc.hash.load_labels(labels_path)
        _labels_loaded = True
        return True
    return False

def is_labels_loaded() -> bool:
    return _labels_loaded
