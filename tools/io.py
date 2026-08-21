"""Compatibility wrapper for :mod:`tools.core.io`."""
from importlib import import_module

_mod = import_module("tools.core.io")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

