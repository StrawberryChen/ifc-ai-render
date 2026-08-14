# 通用场景语义映射

## 数据流

```text
Blender场景（当前）/ SKP解析器（以后）
                  ↓
          raw_scene_inventory.json
                  ↓
  名称 + 材质 + Collection + 几何特征
                  ↓
          Semantic Mapper
                  ↓
          project_manifest.json
                  ↓
       Scene Planner / Blender Executor
```

每个项目都会保存独立 manifest，但不需要为每个项目修改程序。Executor只识别标准类型，不依赖客户原始命名。

## 标准类型

`building`、`sports_field`、`court`、`road`、`pedestrian`、`green_area`、`boundary`、`context_building`、`water`、`parking`、`entrance`、`unknown`。

## 从 Blender 导出

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  -b outputs/sdcc/sdcc.scene.blend \
  --python blender/export_scene_inventory.py -- \
  --project-id sdcc_demo \
  --project-name "SDCC Demo" \
  --output outputs/manifests/sdcc.raw.json
```

## 自动映射并应用项目确认

```bash
python3 semantic/semantic_mapper.py \
  --input outputs/manifests/sdcc.raw.json \
  --rules configs/semantic_mapping_rules.json \
  --overrides data/examples/sdcc_mapping_overrides.json \
  --output outputs/manifests/sdcc.project_manifest.json
```

`mapping_status=auto` 表示规则高置信度识别，`confirmed` 表示使用项目确认，`needs_confirmation` 表示必须由用户或后续 DeepSeek 映射 Agent 判断。

manifest与 Scene Planner inventory 使用相同的 `schema_version=1.0` 和 `objects` 结构，因此可以直接作为 Planner 的 `--inventory` 输入。

## Executor 第一版

Executor只通过 manifest绑定Blender原始对象，绝不靠项目名称硬编码。当前已实现太阳、世界环境、候选相机、渲染尺寸、语义属性写入和新Blend保存：

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  -b outputs/sdcc/sdcc.scene.blend \
  --python blender/scene_executor.py -- \
  --manifest outputs/manifests/sdcc.project_manifest.json \
  --plan outputs/planning/sdcc.scene_plan.json \
  --output-blend outputs/executor/sdcc.planned.blend \
  --report outputs/executor/sdcc.execution_report.json \
  --preview outputs/executor/sdcc.preview.png
```

如果 manifest 仍有未确认对象或引用的 Blender对象不存在，Executor拒绝修改场景。材质资产、植被、人物车辆和亮窗尚未接入时会在报告中明确标记 `planned_not_implemented`。
