# -*- coding: utf-8 -*-
"""pytest 公共配置。

插件在 AstrBot 中以「包」的形式加载（main.py 里使用相对导入），
因此测试也把插件根目录注册成一个合成包，保证相对导入语义一致。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "mcmod_plugin"

if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(PLUGIN_ROOT)]  # type: ignore[attr-defined]
    sys.modules[PACKAGE_NAME] = package

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def class_2524_html() -> str:
    return (FIXTURES / "class_2524.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def class_1188_html() -> str:
    return (FIXTURES / "class_1188.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def modpack_1_html() -> str:
    return (FIXTURES / "modpack_1.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def modpack_897_html() -> str:
    return (FIXTURES / "modpack_897.html").read_text(encoding="utf-8")
