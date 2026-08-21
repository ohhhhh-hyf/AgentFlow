"""Compatibility wrapper for :mod:`tools.exports.mindmap`."""
from importlib import import_module

_mod = import_module("tools.exports.mindmap")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
