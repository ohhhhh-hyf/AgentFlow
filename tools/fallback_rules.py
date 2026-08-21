"""Compatibility wrapper for :mod:`tools.schema.fallback_rules`."""
from importlib import import_module

_mod = import_module("tools.schema.fallback_rules")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
