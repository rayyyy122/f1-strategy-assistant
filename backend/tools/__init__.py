"""Tools 包入口 — 副作用 import 触发各模块的 registry.register 调用。

注：每个 *_tools.py 模块在文件底部直接调用 registry.register。
仅 import registry 并不会触发这些注册，必须显式 import 各模块。
"""

from . import circuit_tools  # noqa: F401
from . import tire_tools  # noqa: F401
from . import session_tools  # noqa: F401
from . import weather_tools  # noqa: F401
from . import strategy_tools  # noqa: F401
from . import web_tools  # noqa: F401
from . import team_driver_tools  # noqa: F401
