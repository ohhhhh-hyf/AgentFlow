"""Compatibility wrapper for :mod:`tools.core.runtime_context`."""
from importlib import import_module

_mod = import_module("tools.core.runtime_context")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

