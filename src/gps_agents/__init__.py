"""GPS Genealogy Agents - Multi-agent genealogical research system.

A GPS (Genealogical Proof Standard) compliant research system using
Semantic Kernel and AutoGen for multi-agent AI coordination.
"""
from __future__ import annotations

__version__ = "0.2.0"

# Lazy imports to avoid circular dependencies
def __getattr__(name: str):
    if name == "gramps":
        from gps_agents import gramps
        return gramps
    if name == "autogen":
        from gps_agents import autogen
        return autogen
    if name == "sources":
        from gps_agents import sources
        return sources
    if name == "models":
        from gps_agents import models
        return models
    if name == "sk":
        from gps_agents import sk
        return sk
    if name == "research":
        from gps_agents import research
        return research
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
