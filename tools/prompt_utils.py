"""Compatibility wrapper for :mod:`tools.core.prompt_utils`."""
from importlib import import_module

_mod = import_module("tools.core.prompt_utils")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

