"""Compatibility wrapper for :mod:`tools.schema.contracts`."""
from importlib import import_module

_mod = import_module("tools.schema.contracts")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
