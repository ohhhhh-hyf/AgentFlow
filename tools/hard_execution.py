"""Compatibility wrapper for :mod:`tools.execution.hard_execution`."""
from importlib import import_module

_mod = import_module("tools.execution.hard_execution")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
