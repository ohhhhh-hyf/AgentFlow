"""Compatibility wrapper for :mod:`tools.templates.template_prompt`."""
from importlib import import_module

_mod = import_module("tools.templates.template_prompt")
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
