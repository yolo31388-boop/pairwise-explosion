"""
爆炸系统 - 核心模块（带bug版本）

已知问题：
- 伤害无距离衰减
- 无视线检测可穿墙
- 衰减线性无最小阈值
- 冲击力不考虑质量只作用玩家
- 范围不考虑高度差特效无变化
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import time


@dataclass
class Config:
    """配置项"""
    pass


class ExplosionSystem:
    """爆炸系统核心类"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._state = {}
        self._history = []

    def update(self, dt: float):
        """每帧更新"""
        pass

    def reset(self):
        """重置状态"""
        self._state = {}
        self._history = []
