"""
爆炸系统 - 核心模块

修复内容：
- calculate_damage()：伤害按距离指数衰减，带最小伤害阈值
- check_line_of_sight()：视线检测，爆炸无法穿墙
- damage_falloff()：指数衰减曲线（近距离高伤害，远距离迅速降低）
- explosion_force()：冲击力考虑目标质量，且作用于所有实体
- area_effect()：范围效果考虑高度差（3D 距离），特效强度随距离变化
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Union
import math
import time

Vec3 = Tuple[float, float, float]

_EPS = 1e-9


def _to_vec3(value) -> Vec3:
    """把任意 (x, y, z) 序列/带 x,y,z 属性的对象转成三元组。"""
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return (float(value.x), float(value.y), float(value.z))
    x, y, z = value
    return (float(x), float(y), float(z))


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(v: Vec3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _normalize(v: Vec3) -> Vec3:
    n = _length(v)
    if n < _EPS:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def _distance(a: Vec3, b: Vec3) -> float:
    return _length(_sub(a, b))


@dataclass
class Config:
    """爆炸配置项"""

    base_damage: float = 100.0        # 爆炸中心的基础伤害
    radius: float = 20.0              # 爆炸影响半径（米）
    falloff_rate: float = 3.0         # 指数衰减系数，越大衰减越快
    min_damage: float = 0.0           # 最小伤害阈值，低于该值记为 0
    base_force: float = 1000.0        # 爆炸中心的基础冲击力
    reference_mass: float = 1.0       # 参考质量，位移按 reference_mass/mass 缩放
    base_effect_intensity: float = 1.0  # 爆炸中心的特效强度
    min_effect_intensity: float = 0.0   # 特效强度下限


@dataclass
class Obstacle:
    """轴对齐包围盒障碍物（墙体、掩体等）"""

    min_point: Vec3
    max_point: Vec3

    def __post_init__(self):
        self.min_point = _to_vec3(self.min_point)
        self.max_point = _to_vec3(self.max_point)


@dataclass
class Entity:
    """受爆炸影响的实体（玩家、NPC、场景物体）"""

    id: str = ""
    position: Vec3 = (0.0, 0.0, 0.0)
    mass: float = 1.0
    is_player: bool = False

    def __post_init__(self):
        self.position = _to_vec3(self.position)
        self.mass = max(float(self.mass), _EPS)


@dataclass
class ForceResult:
    """单个实体受到的冲击力结果"""

    entity_id: str
    direction: Vec3            # 单位方向向量：爆炸中心 -> 目标
    force: float               # 冲击力大小（已按距离衰减）
    displacement: Vec3         # 位移向量，质量越大位移越小
    new_position: Vec3         # 应用位移后的位置


@dataclass
class AreaEffect:
    """某位置处的范围效果"""

    position: Vec3
    distance: float            # 3D 距离（含高度差）
    in_range: bool
    intensity: float           # 特效强度，随距离增大而减小
    effect_scale: float        # 特效缩放系数


class ExplosionSystem:
    """爆炸系统核心类"""

    def __init__(self, config: Optional[Union[Dict, Config]] = None):
        if config is None:
            self.config = Config()
        elif isinstance(config, Config):
            self.config = config
        else:
            valid = {f for f in Config.__dataclass_fields__}
            self.config = Config(**{k: v for k, v in config.items() if k in valid})
        self._state = {}
        self._history = []

    # ------------------------------------------------------------------
    # 伤害计算
    # ------------------------------------------------------------------
    def damage_falloff(self, distance: float, radius: Optional[float] = None,
                       falloff_rate: Optional[float] = None) -> float:
        """指数衰减系数：distance=0 时为 1，随距离指数下降，超出半径为 0。"""
        radius = self.config.radius if radius is None else float(radius)
        falloff_rate = self.config.falloff_rate if falloff_rate is None else float(falloff_rate)
        distance = max(float(distance), 0.0)
        if radius <= 0.0:
            return 1.0 if distance <= 0.0 else 0.0
        if distance >= radius:
            return 0.0
        return math.exp(-falloff_rate * distance / radius)

    def calculate_damage(self, distance: float, base_damage: Optional[float] = None,
                         radius: Optional[float] = None,
                         falloff_rate: Optional[float] = None,
                         min_damage: Optional[float] = None) -> float:
        """按距离指数衰减计算伤害，低于最小伤害阈值时记为 0。"""
        base_damage = self.config.base_damage if base_damage is None else float(base_damage)
        min_damage = self.config.min_damage if min_damage is None else float(min_damage)
        damage = base_damage * self.damage_falloff(distance, radius, falloff_rate)
        if damage < min_damage:
            return 0.0
        return damage

    # ------------------------------------------------------------------
    # 视线检测
    # ------------------------------------------------------------------
    def check_line_of_sight(self, start, end, obstacles=None) -> bool:
        """检查 start 到 end 之间是否无遮挡（True 表示视线通畅）。"""
        start = _to_vec3(start)
        end = _to_vec3(end)
        for obstacle in self._normalize_obstacles(obstacles):
            if self._segment_intersects_aabb(start, end, obstacle):
                return False
        return True

    @staticmethod
    def _normalize_obstacles(obstacles) -> List[Obstacle]:
        result = []
        for obstacle in obstacles or []:
            if isinstance(obstacle, Obstacle):
                result.append(obstacle)
            elif isinstance(obstacle, dict):
                min_point = obstacle.get("min_point", obstacle.get("min"))
                max_point = obstacle.get("max_point", obstacle.get("max"))
                result.append(Obstacle(min_point, max_point))
            else:
                min_point, max_point = obstacle
                result.append(Obstacle(min_point, max_point))
        return result

    @staticmethod
    def _segment_intersects_aabb(start: Vec3, end: Vec3, obstacle: Obstacle) -> bool:
        """slab 法判断线段是否与 AABB 相交（含内部）。"""
        direction = _sub(end, start)
        t_min, t_max = 0.0, 1.0
        for axis in range(3):
            lo = obstacle.min_point[axis]
            hi = obstacle.max_point[axis]
            d = direction[axis]
            s = start[axis]
            if abs(d) < _EPS:
                if s < lo or s > hi:
                    return False
            else:
                t1 = (lo - s) / d
                t2 = (hi - s) / d
                if t1 > t2:
                    t1, t2 = t2, t1
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                if t_min > t_max:
                    return False
        return True

    # ------------------------------------------------------------------
    # 爆炸冲击力
    # ------------------------------------------------------------------
    def explosion_force(self, entity, explosion_center=None,
                        base_force: Optional[float] = None,
                        radius: Optional[float] = None,
                        falloff_rate: Optional[float] = None,
                        reference_mass: Optional[float] = None,
                        obstacles=None) -> Optional[ForceResult]:
        """计算实体受到的冲击力。

        - 方向为爆炸中心指向目标；
        - 力的大小随距离指数衰减；
        - 位移与质量成反比（质量越大被吹飞的距离越短）；
        - 对玩家和场景物体等所有实体生效；
        - 被障碍物完全遮挡时不受力（返回 None）。
        """
        entity = self._normalize_entity(entity)
        center = _to_vec3(explosion_center) if explosion_center is not None else (0.0, 0.0, 0.0)
        base_force = self.config.base_force if base_force is None else float(base_force)
        reference_mass = self.config.reference_mass if reference_mass is None else float(reference_mass)

        offset = _sub(entity.position, center)
        distance = _length(offset)
        if not self.check_line_of_sight(center, entity.position, obstacles):
            return None
        falloff = self.damage_falloff(distance, radius, falloff_rate)
        if falloff <= 0.0:
            return None

        direction = _normalize(offset)
        force = base_force * falloff
        scale = force * reference_mass / entity.mass
        displacement = (direction[0] * scale, direction[1] * scale, direction[2] * scale)
        new_position = (entity.position[0] + displacement[0],
                        entity.position[1] + displacement[1],
                        entity.position[2] + displacement[2])
        return ForceResult(entity_id=entity.id, direction=direction, force=force,
                           displacement=displacement, new_position=new_position)

    @staticmethod
    def _normalize_entity(entity) -> Entity:
        if isinstance(entity, Entity):
            return entity
        if isinstance(entity, dict):
            return Entity(
                id=str(entity.get("id", "")),
                position=entity.get("position", (0.0, 0.0, 0.0)),
                mass=entity.get("mass", 1.0),
                is_player=bool(entity.get("is_player", False)),
            )
        return Entity(
            id=str(getattr(entity, "id", "")),
            position=getattr(entity, "position", (0.0, 0.0, 0.0)),
            mass=getattr(entity, "mass", 1.0),
            is_player=bool(getattr(entity, "is_player", False)),
        )

    # ------------------------------------------------------------------
    # 范围效果
    # ------------------------------------------------------------------
    def area_effect(self, position, explosion_center=None,
                    radius: Optional[float] = None,
                    base_intensity: Optional[float] = None,
                    min_intensity: Optional[float] = None) -> AreaEffect:
        """计算某位置处的范围效果。

        - 使用 3D 距离（含高度差），高台上的目标不会受到满额效果；
        - 特效强度随距离线性衰减，超出半径为 0。
        """
        position = _to_vec3(position)
        center = _to_vec3(explosion_center) if explosion_center is not None else (0.0, 0.0, 0.0)
        radius = self.config.radius if radius is None else float(radius)
        base_intensity = self.config.base_effect_intensity if base_intensity is None else float(base_intensity)
        min_intensity = self.config.min_effect_intensity if min_intensity is None else float(min_intensity)

        distance = _distance(position, center)
        in_range = distance < radius if radius > 0 else distance <= 0.0
        if in_range and radius > 0:
            intensity = base_intensity * (1.0 - distance / radius)
        elif in_range:
            intensity = base_intensity
        else:
            intensity = 0.0
        intensity = max(intensity, min_intensity if in_range else 0.0)
        return AreaEffect(position=position, distance=distance, in_range=in_range,
                          intensity=intensity, effect_scale=intensity)

    # ------------------------------------------------------------------
    # 综合引爆
    # ------------------------------------------------------------------
    def detonate(self, center, entities=None, obstacles=None,
                 apply_displacement: bool = True) -> Dict:
        """在 center 处引爆，返回每个实体的伤害与冲击力结果。"""
        center = _to_vec3(center)
        results = {}
        for raw in entities or []:
            entity = self._normalize_entity(raw)
            distance = _distance(entity.position, center)
            visible = self.check_line_of_sight(center, entity.position, obstacles)
            damage = self.calculate_damage(distance) if visible else 0.0
            force_result = self.explosion_force(entity, center, obstacles=obstacles)
            if apply_displacement and force_result is not None and isinstance(raw, Entity):
                raw.position = force_result.new_position
            results[entity.id] = {
                "entity": entity,
                "distance": distance,
                "visible": visible,
                "damage": damage,
                "force": force_result,
            }
        record = {"center": center, "time": time.time(), "results": results}
        self._history.append(record)
        return record

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def update(self, dt: float):
        """每帧更新"""
        self._state["last_dt"] = dt

    def reset(self):
        """重置状态"""
        self._state = {}
        self._history = []
