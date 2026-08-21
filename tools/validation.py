"""Compatibility wrapper for :mod:`tools.schema.validation`."""
from importlib import import_module

_mod = import_module("tools.schema.validation")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
