"""
爆炸系统 - 验收测试

运行方式：python -m pytest tests/test_explosion.py -q
共 12 个测试用例
"""
import pytest
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from explosion.system import ExplosionSystem, Config, Entity, Obstacle


class TestExplosionSystem:
    """爆炸系统测试套件"""

    def setup_method(self):
        """每个测试前的初始化"""
        self.system = ExplosionSystem(Config(
            base_damage=100.0, radius=20.0, falloff_rate=3.0,
            min_damage=5.0, base_force=1000.0, reference_mass=1.0,
        ))

    # --- calculate_damage / damage_falloff：指数衰减与最小阈值 ---

    def test_case_01(self):
        """爆炸中心受到满额基础伤害"""
        assert self.system.calculate_damage(0) == pytest.approx(100.0)

    def test_case_02(self):
        """1米处伤害远大于10米处，距离衰减生效"""
        near = self.system.calculate_damage(1)
        far = self.system.calculate_damage(10)
        assert near > far
        assert near == pytest.approx(100.0 * math.exp(-3.0 * 1 / 20.0))
        assert far == pytest.approx(100.0 * math.exp(-3.0 * 10 / 20.0))

    def test_case_03(self):
        """衰减曲线为指数：伤害取对数后与距离成线性关系"""
        damages = [self.system.calculate_damage(d) for d in range(1, 8)]
        logs = [math.log(d) for d in damages]
        slopes = [(logs[i + 1] - logs[i]) for i in range(len(logs) - 1)]
        assert all(s < 0 for s in slopes)
        assert max(slopes) - min(slopes) == pytest.approx(0.0, abs=1e-9)

    def test_case_04(self):
        """低于最小伤害阈值（含超出爆炸半径）的伤害为0"""
        # falloff_rate=5 时 19 米处伤害约 0.86，低于 min_damage=5 的阈值
        assert self.system.calculate_damage(19, falloff_rate=5.0) == 0.0
        assert self.system.calculate_damage(50) == 0.0
        assert self.system.calculate_damage(15) > 0.0

    # --- check_line_of_sight：视线阻挡 ---

    def test_case_05(self):
        """无障碍物时视线通畅"""
        assert self.system.check_line_of_sight((0, 0, 0), (10, 0, 0)) is True

    def test_case_06(self):
        """墙体位于爆炸中心与目标之间时视线被阻挡"""
        wall = Obstacle((4, -2, -2), (6, 2, 2))
        assert self.system.check_line_of_sight((0, 0, 0), (10, 0, 0), [wall]) is False

    def test_case_07(self):
        """墙后的目标受到0伤害，掩体有效；绕过墙体的目标正常受伤"""
        wall = Obstacle((4, -2, -2), (6, 2, 2))
        behind = Entity(id="behind", position=(10, 0, 0), mass=70.0, is_player=True)
        aside = Entity(id="aside", position=(10, 10, 0), mass=70.0, is_player=True)
        results = self.system.detonate((0, 0, 0), [behind, aside], [wall],
                                       apply_displacement=False)["results"]
        assert results["behind"]["damage"] == 0.0
        assert results["behind"]["force"] is None
        assert results["aside"]["damage"] > 0.0

    # --- explosion_force：考虑质量、作用所有实体 ---

    def test_case_08(self):
        """冲击力方向从爆炸中心指向目标"""
        target = Entity(id="p", position=(3, 4, 0), mass=1.0, is_player=True)
        result = self.system.explosion_force(target, (0, 0, 0))
        assert result.direction == pytest.approx((0.6, 0.8, 0.0))

    def test_case_09(self):
        """位移与质量成反比：轻物体被吹飞更远，力的大小相同"""
        light = Entity(id="light", position=(10, 0, 0), mass=10.0, is_player=False)
        heavy = Entity(id="heavy", position=(10, 0, 0), mass=100.0, is_player=False)
        r_light = self.system.explosion_force(light, (0, 0, 0))
        r_heavy = self.system.explosion_force(heavy, (0, 0, 0))
        assert r_light.force == pytest.approx(r_heavy.force)
        assert (r_light.displacement[0] ==
                pytest.approx(10.0 * r_heavy.displacement[0]))

    def test_case_10(self):
        """冲击力同样作用于非玩家场景物体（箱子），且整体引爆会推动它"""
        crate = Entity(id="crate", position=(5, 0, 0), mass=5.0, is_player=False)
        result = self.system.explosion_force(crate, (0, 0, 0))
        assert result is not None
        assert result.force > 0.0
        self.system.detonate((0, 0, 0), [crate])
        assert crate.position[0] > 5.0

    # --- area_effect：高度差与特效随距离变化 ---

    def test_case_11(self):
        """高度差计入距离：正上方10米平台上的目标不是满额效果"""
        above = self.system.area_effect((0, 0, 10), (0, 0, 0), radius=20.0)
        ground_far = self.system.area_effect((10, 0, 0), (0, 0, 0), radius=20.0)
        center = self.system.area_effect((0, 0, 0), (0, 0, 0), radius=20.0)
        assert above.distance == pytest.approx(10.0)
        assert above.intensity < center.intensity
        assert above.intensity == pytest.approx(ground_far.intensity)

    def test_case_12(self):
        """特效强度随距离增大而减小，超出半径无特效"""
        center = self.system.area_effect((0, 0, 0), radius=20.0)
        near = self.system.area_effect((2, 0, 0), radius=20.0)
        far = self.system.area_effect((15, 0, 0), radius=20.0)
        outside = self.system.area_effect((30, 0, 0), radius=20.0)
        assert center.intensity > near.intensity > far.intensity > 0.0
        assert outside.in_range is False
        assert outside.intensity == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
