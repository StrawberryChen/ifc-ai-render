# 建筑效果图控制系统架构

## 核心原则

系统不让语言模型直接编写或执行 Blender Python。语言模型只生成受约束的 `scene_plan.json`，所有操作先经过参数校验，再由确定性的 Blender Executor 执行。这样才能支持前端预览、局部调整、撤销和项目复现。

## 数据流

```text
SketchUp/中间格式
  -> 项目场景清单（对象ID、类型、边界、材质、相机）
  -> DeepSeek Planner（需求 + 工具能力 + 资产库 + 专业规则）
  -> scene_plan.json
  -> Blender Executor
  -> 低分辨率预览与结构通道
  -> 用户局部调整 / 新版本
  -> 最终渲染与受控AI增强
```

## 三份稳定契约

- `schemas/scene_plan_v1.json`：项目场景状态，前端和执行器共同读取。
- `schemas/blender_tools_v1.json`：允许用户或 Planner 修改的动作、参数范围、控件类型及实现状态。
- `assets/registry/asset_registry.json`：系统实际拥有的材质、树木、灯具等资产，Planner 不得虚构资产。

专业判断规则位于 `playbooks/architectural_visualization_v1.json`。Planner 的提示词由上述实时数据动态组装，不维护一份容易过期的超长 Prompt。

## 前端局部修改

当前 Streamlit 原型会按 Tool Schema 自动生成控件。每次调整只修改 Scene Plan 中对应字段，并保存新 revision；“撤销”恢复上一份计划。下一阶段前端可直接复用同一契约实现：

1. 左侧三维或渲染预览；
2. 点击对象或选择功能区；
3. 右侧属性控件；
4. 提交 patch，生成快速预览；
5. 对比版本并确认后进入最终渲染。

## 能力状态

Tool Schema 中 `implemented` 表示 Blender Executor 已能执行，`planned` 表示计划和前端字段已经稳定，但执行模块尚待接入。页面必须显示该状态，不能让用户误以为未实现的能力已经生效。

## 为什么不是只写一份 Prompt

高质量结果依赖可执行资产、项目几何、参数边界和质量检查。Prompt 负责理解意图，Schema 负责限制动作，Executor 负责确定性执行，版本系统负责可回退。四者分离后，未来更换语言模型或前端框架不会推翻 Blender 工作流。
