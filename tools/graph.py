"""Compatibility wrapper for :mod:`tools.exports.knowledge_graph`."""
from importlib import import_module

_mod = import_module("tools.exports.knowledge_graph")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
