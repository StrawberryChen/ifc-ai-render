# 建筑效果图 Scene Planner

## 为什么先做规划器

规划器不依赖 SKP 文件格式。它接收标准化场景清单、自然语言需求和参考图分析，输出 Blender 执行器可以消费的 `scene_plan.json`。当前使用模拟校园清单；获得 SKP SDK 后，解析器只需生成相同格式的 inventory。

```text
SKP解析器（以后） ─┐
手工/模拟清单（现在）├→ Scene Planner → scene_plan.json → Blender Executor
客户需求与参考图 ───┘
```

## 输入与输出

- `campus_scene_inventory.json`：权威设计对象及其语义类型。
- `campus_visual_brief.json`：时间、氛围、景观密度和交付要求。
- `scene_plan.json`：相机、灯光、材质、景观、人物车辆、渲染通道和 AI 后处理计划。

所有设计几何默认 `preserve_geometry=true`。规划器只能为已有对象分配表现规则，不能创造或修改建筑、运动场和道路设计。

## 离线基线

无需模型和 API，先验证数据合同：

```bash
python3 planning/scene_planner.py \
  --inventory data/examples/campus_scene_inventory.json \
  --brief data/examples/campus_visual_brief.json \
  --output outputs/planning/campus_scene_plan.json
```

## 接入 Qwen 等兼容接口

规划器支持 OpenAI-compatible `/chat/completions` 接口，不绑定特定厂商：

```bash
export SCENE_PLANNER_API_KEY="临时密钥"
export SCENE_PLANNER_ENDPOINT="服务商提供的兼容接口根地址"
export SCENE_PLANNER_MODEL="qwen-plus"

python3 planning/scene_planner.py \
  --inventory data/examples/campus_scene_inventory.json \
  --brief data/examples/campus_visual_brief.json \
  --output outputs/planning/campus_scene_plan.ai.json \
  --provider openai-compatible
```

密钥只放环境变量，不写入配置或 Git。模型返回后仍执行本地验证，阻止未知对象 ID 和结构不完整的计划进入 Blender。

## 后续接口

Blender Executor 将按计划实现：

1. PBR材质预设映射；
2. 绿地区域资产散布及建筑/道路避让；
3. 单一太阳方向、天空、亮窗和路灯；
4. 相机候选构建及低分辨率预览；
5. Beauty、Depth、Normal、Object ID、Material ID、Shadow和Edge输出。
