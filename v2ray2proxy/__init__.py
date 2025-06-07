"""
v2ray2proxy - Convert V2Ray configs to usable proxies for HTTP clients
"""
from .sync_proxy import V2RayProxy
from .async_proxy import AsyncV2RayProxy

VERSION = "0.1"

__all__ = ["V2RayProxy", "AsyncV2RayProxy", "VERSION"]
