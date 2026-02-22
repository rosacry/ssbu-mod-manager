import os
import pyprc
from src.utils.resource_path import resource_path

_labels_loaded = False

def load_param_labels():
    """Load ParamLabels.csv for hash resolution. Call once at startup."""
    global _labels_loaded
    if _labels_loaded:
        return True

    labels_path = resource_path("ParamLabels.csv")
    if os.path.exists(labels_path):
        pyprc.hash.load_labels(labels_path)
        _labels_loaded = True
        return True
    return False

def is_labels_loaded() -> bool:
    return _labels_loaded
