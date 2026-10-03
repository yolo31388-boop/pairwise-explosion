"""
爆炸系统 - 核心模块（修复版）

修复内容：
- 伤害按距离指数衰减，并带最小伤害阈值（低于阈值判定为无伤害）
- 爆炸前做视线检测，障碍物（墙体/掩体）可完全阻挡伤害
- 冲击力按目标质量分配（质量越大位移越小），且作用于所有物体（含场景物体）
- 范围效果使用三维距离（含高度差），特效强度随距离衰减
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import time

Vector3 = Tuple[float, float, float]

# 指数衰减系数：distance = radius 时衰减到 max_damage * exp(-FALLOFF_RATE)
FALLOFF_RATE = 3.0


@dataclass
class Config:
    """配置项"""
    max_damage: float = 100.0
    radius: float = 15.0
    min_damage: float = 5.0
    base_force: float = 1000.0


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(v: Vector3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _distance(a: Vector3, b: Vector3) -> float:
    return _length(_sub(a, b))


def _normalize(v: Vector3) -> Vector3:
    n = _length(v)
    if n == 0.0:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


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

    # ------------------------------------------------------------------
    # 伤害衰减
    # ------------------------------------------------------------------
    def damage_falloff(self, distance: float, max_damage: float,
                       radius: float, min_damage: float = 0.0) -> float:
        """指数伤害衰减。

        - distance <= 0 时造成全额伤害
        - distance >= radius 时无伤害
        - 中间按 max_damage * exp(-FALLOFF_RATE * distance / radius) 衰减
        - 衰减结果低于 min_damage 阈值时判定为无伤害（返回 0）
        """
        if distance < 0.0:
            distance = 0.0
        if distance >= radius:
            return 0.0
        damage = max_damage * math.exp(-FALLOFF_RATE * distance / radius)
        if damage < min_damage:
            return 0.0
        return damage

    # ------------------------------------------------------------------
    # 视线检测
    # ------------------------------------------------------------------
    def check_line_of_sight(self, start: Vector3, end: Vector3,
                            obstacles: Optional[List[Dict]] = None) -> bool:
        """检查 start 到 end 之间是否无遮挡。

        障碍物支持两种形式：
        - 轴对齐盒（墙体/掩体）：{"min": (x,y,z), "max": (x,y,z)}
        - 球体：{"center": (x,y,z), "radius": r}
        返回 True 表示视线通畅，False 表示被阻挡。
        """
        if not obstacles:
            return True
        for obs in obstacles:
            if "min" in obs and "max" in obs:
                if self._segment_hits_aabb(start, end, obs["min"], obs["max"]):
                    return False
            elif "center" in obs and "radius" in obs:
                if self._segment_hits_sphere(start, end, obs["center"], obs["radius"]):
                    return False
        return True

    @staticmethod
    def _segment_hits_aabb(start: Vector3, end: Vector3,
                           bmin: Vector3, bmax: Vector3) -> bool:
        """slab 法判断线段是否与 AABB 相交"""
        t_min, t_max = 0.0, 1.0
        for i in range(3):
            d = end[i] - start[i]
            if abs(d) < 1e-12:
                if start[i] < bmin[i] or start[i] > bmax[i]:
                    return False
                continue
            inv = 1.0 / d
            t1 = (bmin[i] - start[i]) * inv
            t2 = (bmax[i] - start[i]) * inv
            if t1 > t2:
                t1, t2 = t2, t1
            t_min = max(t_min, t1)
            t_max = min(t_max, t2)
            if t_min > t_max:
                return False
        return True

    @staticmethod
    def _segment_hits_sphere(start: Vector3, end: Vector3,
                             center: Vector3, radius: float) -> bool:
        """判断线段与球体是否相交"""
        d = _sub(end, start)
        f = _sub(start, center)
        a = d[0] * d[0] + d[1] * d[1] + d[2] * d[2]
        if a < 1e-12:
            return _length(f) <= radius
        b = 2.0 * (f[0] * d[0] + f[1] * d[1] + f[2] * d[2])
        c = f[0] * f[0] + f[1] * f[1] + f[2] * f[2] - radius * radius
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return False
        sq = math.sqrt(disc)
        t1 = (-b - sq) / (2.0 * a)
        t2 = (-b + sq) / (2.0 * a)
        return (0.0 <= t1 <= 1.0) or (0.0 <= t2 <= 1.0) or (t1 < 0.0 and t2 > 1.0)

    # ------------------------------------------------------------------
    # 伤害计算
    # ------------------------------------------------------------------
    def calculate_damage(self, explosion_pos: Vector3, target_pos: Vector3,
                         max_damage: float = 100.0, radius: float = 15.0,
                         obstacles: Optional[List[Dict]] = None,
                         min_damage: float = 5.0) -> float:
        """计算目标受到的爆炸伤害。

        - 按三维距离做指数衰减
        - 低于 min_damage 阈值或超出半径时无伤害
        - 爆炸点与目标之间存在障碍物时伤害被完全阻挡
        """
        if not self.check_line_of_sight(explosion_pos, target_pos, obstacles):
            return 0.0
        distance = _distance(explosion_pos, target_pos)
        return self.damage_falloff(distance, max_damage, radius, min_damage)

    # ------------------------------------------------------------------
    # 爆炸冲击力
    # ------------------------------------------------------------------
    def explosion_force(self, center: Vector3, objects: List[Dict],
                        force: float = 1000.0, radius: float = 15.0,
                        obstacles: Optional[List[Dict]] = None) -> Dict:
        """计算爆炸对物体的冲击冲量。

        - 方向：从爆炸中心指向目标
        - 大小：随距离指数衰减，并除以目标质量（越轻被吹得越远）
        - 作用于所有带 position/mass 的物体（玩家与场景物体一视同仁）
        - 被障碍物完全遮挡的物体不受力
        返回 {object_id: (fx, fy, fz)}，id 缺省时用列表下标。
        """
        impulses = {}
        for index, obj in enumerate(objects):
            pos = obj.get("position")
            if pos is None:
                continue
            mass = obj.get("mass", 1.0)
            if mass <= 0.0:
                continue
            distance = _distance(center, pos)
            if distance >= radius:
                continue
            if not self.check_line_of_sight(center, pos, obstacles):
                continue
            falloff = math.exp(-FALLOFF_RATE * distance / radius)
            magnitude = force * falloff / mass
            direction = _normalize(_sub(pos, center))
            obj_id = obj.get("id", index)
            impulses[obj_id] = (direction[0] * magnitude,
                                direction[1] * magnitude,
                                direction[2] * magnitude)
        return impulses

    # ------------------------------------------------------------------
    # 范围效果
    # ------------------------------------------------------------------
    def area_effect(self, center: Vector3, radius: float,
                    targets: Optional[List[Dict]] = None,
                    obstacles: Optional[List[Dict]] = None) -> List[Dict]:
        """计算范围内每个目标受到的爆炸效果强度。

        - 使用三维距离（高度差会削弱效果，高台上不会吃满额伤害）
        - 特效强度 scale 随距离指数衰减（0~1），中心为 1，边缘趋近 0
        - 被障碍物遮挡的目标 scale 为 0
        返回 [{"id", "distance", "scale"}, ...]
        """
        results = []
        for index, target in enumerate(targets or []):
            pos = target.get("position")
            if pos is None:
                continue
            distance = _distance(center, pos)
            if distance >= radius:
                scale = 0.0
            elif not self.check_line_of_sight(center, pos, obstacles):
                scale = 0.0
            else:
                scale = math.exp(-FALLOFF_RATE * distance / radius)
            results.append({
                "id": target.get("id", index),
                "distance": distance,
                "scale": scale,
            })
        return results
