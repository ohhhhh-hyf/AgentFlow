"""Compatibility wrapper for :mod:`tools.exports.outputs`."""
from importlib import import_module

_mod = import_module("tools.exports.outputs")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
