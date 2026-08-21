"""Compatibility wrapper for :mod:`tools.core.domain_engine_text`."""
from importlib import import_module

_mod = import_module("tools.core.domain_engine_text")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

