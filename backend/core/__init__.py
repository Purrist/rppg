# core/__init__.py
# 核心模块 - 只导出SystemCore

from .system_core import SystemCore, init_system_core, get_system_core

__all__ = ["SystemCore", "init_system_core", "get_system_core"]
