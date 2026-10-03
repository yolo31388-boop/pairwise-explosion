# 爆炸系统

## 项目描述

爆炸系统的bug修复项目。核心模块 `explosion/system.py` 存在多个已知bug，需要修复后使测试全部通过。

## 已知问题

- 伤害无距离衰减
- 无视线检测可穿墙
- 衰减线性无最小阈值
- 冲击力不考虑质量只作用玩家
- 范围不考虑高度差特效无变化

## 项目结构

```
├── explosion/system.py       # 核心模块（带bug）
├── tests/test_explosion.py    # 验收测试（红态）
├── pyproject.toml          # 项目配置
└── README.md               # 说明文档
```

## 运行测试

```bash
python -m pytest tests/test_explosion.py -q
```

修复目标：所有 12 个测试全部通过。

## 技术要求

- 纯Python标准库，不引入第三方依赖
- 不修改测试文件
- 保持现有API接口不变
- 修复所有已知bug
