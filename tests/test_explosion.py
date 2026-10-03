"""
爆炸系统 - 验收测试

运行方式：python -m pytest tests/test_explosion.py -q
共 12 个测试用例
"""
import pytest
import sys
import math
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from explosion.system import ExplosionSystem


class TestExplosionSystem:
    """爆炸系统测试套件"""

    def setup_method(self):
        """每个测试前的初始化"""
        self.system = ExplosionSystem()

    def test_case_01(self):
        """近距离伤害应远大于远距离伤害（修复固定伤害）"""
        near = self.system.calculate_damage((0, 0, 0), (1, 0, 0))
        far = self.system.calculate_damage((0, 0, 0), (10, 0, 0))
        assert near > far * 3
        assert near == pytest.approx(100 * math.exp(-0.2), rel=1e-6)
        assert far == pytest.approx(100 * math.exp(-2.0), rel=1e-6)

    def test_case_02(self):
        """衰减曲线应为指数而非线性：半径中点处伤害应远低于最大值的一半"""
        midpoint = self.system.damage_falloff(7.5, 100.0, 15.0, min_damage=0.0)
        assert midpoint < 50.0
        assert midpoint == pytest.approx(100.0 * math.exp(-1.5), rel=1e-6)

    def test_case_03(self):
        """低于最小伤害阈值时应无伤害（修复远处总有 1 点伤害）"""
        d12 = self.system.damage_falloff(12.0, 100.0, 15.0, min_damage=10.0)
        assert d12 == 0.0
        d8 = self.system.damage_falloff(8.0, 100.0, 15.0, min_damage=10.0)
        assert d8 >= 10.0

    def test_case_04(self):
        """超出爆炸半径的目标不受任何伤害"""
        assert self.system.calculate_damage((0, 0, 0), (15, 0, 0)) == 0.0
        assert self.system.damage_falloff(20.0, 100.0, 15.0) == 0.0

    def test_case_05(self):
        """视线被墙阻挡时，墙后目标不受伤害（修复穿墙伤害）"""
        wall = {"min": (4.5, -1.0, -1.0), "max": (5.5, 1.0, 1.0)}
        assert self.system.calculate_damage(
            (0, 0, 0), (10, 0, 0), obstacles=[wall]) == 0.0

    def test_case_06(self):
        """无遮挡时视线通畅，目标正常受到伤害"""
        wall = {"min": (4.5, -5.0, -5.0), "max": (5.5, -4.0, -4.0)}
        assert self.system.check_line_of_sight((0, 0, 0), (10, 0, 0), [wall])
        damage = self.system.calculate_damage(
            (0, 0, 0), (10, 0, 0), obstacles=[wall])
        assert damage == pytest.approx(100 * math.exp(-2.0), rel=1e-6)

    def test_case_07(self):
        """check_line_of_sight 对横亘墙体返回 False，无障碍物返回 True"""
        wall = {"min": (-1.0, -1.0, 4.5), "max": (1.0, 1.0, 5.5)}
        assert not self.system.check_line_of_sight((0, 0, 0), (0, 0, 10), [wall])
        assert self.system.check_line_of_sight((0, 0, 0), (0, 0, 10), [])

    def test_case_08(self):
        """同等距离下，轻物体受到的冲量应大于重物体（修复忽略质量）"""
        objects = [
            {"id": "heavy", "position": (5, 0, 0), "mass": 50.0},
            {"id": "light", "position": (-5, 0, 0), "mass": 10.0},
        ]
        impulses = self.system.explosion_force((0, 0, 0), objects, force=1000.0)
        assert abs(impulses["light"][0]) == pytest.approx(
            5.0 * abs(impulses["heavy"][0]), rel=1e-6)

    def test_case_09(self):
        """冲击力应同时作用于玩家和场景物体（修复只作用玩家）"""
        objects = [
            {"id": "player", "position": (5, 0, 0), "mass": 70.0, "type": "player"},
            {"id": "crate", "position": (0, 5, 0), "mass": 20.0, "type": "prop"},
        ]
        impulses = self.system.explosion_force((0, 0, 0), objects)
        assert "player" in impulses
        assert "crate" in impulses
        assert any(v != 0.0 for v in impulses["crate"])

    def test_case_10(self):
        """冲击力方向必须从爆炸中心指向目标，且被墙挡住的物体不受力"""
        objects = [{"id": "east", "position": (5, 0, 0), "mass": 10.0}]
        impulses = self.system.explosion_force((0, 0, 0), objects)
        assert impulses["east"][0] > 0.0
        wall = {"min": (4.5, -1.0, -1.0), "max": (5.5, 1.0, 1.0)}
        blocked = self.system.explosion_force(
            (0, 0, 0), objects, obstacles=[wall])
        assert "east" not in blocked

    def test_case_11(self):
        """范围效果考虑高度差：上方高台目标的效果应远低于同平面目标"""
        targets = [
            {"id": "ground", "position": (1.0, 0.0, 0.0)},
            {"id": "platform", "position": (0.0, 0.0, 10.0)},
        ]
        effects = {e["id"]: e for e in
                   self.system.area_effect((0, 0, 0), 15.0, targets)}
        assert effects["platform"]["distance"] == pytest.approx(10.0)
        assert effects["platform"]["scale"] < effects["ground"]["scale"]
        assert effects["platform"]["scale"] == pytest.approx(
            math.exp(-2.0), rel=1e-6)

    def test_case_12(self):
        """综合：特效随距离衰减，且墙后目标特效为零"""
        wall = {"min": (-5.5, -1.0, -1.0), "max": (-4.5, 1.0, 1.0)}
        targets = [
            {"id": "near", "position": (1, 0, 0)},
            {"id": "far", "position": (10, 0, 0)},
            {"id": "behind_wall", "position": (-10, 0, 0)},
        ]
        effects = {e["id"]: e for e in
                   self.system.area_effect((0, 0, 0), 15.0, targets,
                                           obstacles=[wall])}
        assert 1.0 > effects["near"]["scale"] > effects["far"]["scale"] > 0.0
        assert effects["behind_wall"]["scale"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
