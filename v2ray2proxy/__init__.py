"""
v2ray2proxy - Convert V2Ray configs to usable proxies for HTTP clients
"""
from .base import V2RayCore, V2RayProxy, V2RayPool

VERSION = "0.2.1"

__all__ = ["V2RayCore", "V2RayProxy", "V2RayPool", "VERSION"]
