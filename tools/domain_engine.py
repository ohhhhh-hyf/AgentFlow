"""Compatibility wrapper for :mod:`tools.core.domain_engine`."""
from importlib import import_module

_mod = import_module("tools.core.domain_engine")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

