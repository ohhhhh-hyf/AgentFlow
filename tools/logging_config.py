"""Compatibility wrapper for :mod:`tools.core.logging_config`."""
from importlib import import_module

_mod = import_module("tools.core.logging_config")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

