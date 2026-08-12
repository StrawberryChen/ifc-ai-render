# IFC AI Render

将 IFC/BIM 结构先转为可验证的白模图和深度图，再用 Qwen-Image 与 Depth ControlNet 生成建筑效果图的原型。

## 工作流

```text
IFC -> IfcOpenShell几何 -> OBJ -> Blender相机 -> 16位深度图
                                              |
自然语言设计描述 -----------------------------+-> Qwen-Image + Depth ControlNet -> 效果图
```

第一阶段不训练模型。深度图负责约束建筑体量和透视，文本负责材质、风格、景观、天气和灯光。

## 1. 本地生成 IFC 深度图

需要 Python 3.11 和 Blender。

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_white_model.py data/samples/Building-Architecture.ifc
```

主要输出：

- `outputs/white_model/*.white.png`：白模预览
- `outputs/white_model/*.depth.png`：与白模完全对齐的 16 位深度条件
- `outputs/white_model/*.camera.json`：相机参数

## 2. Colab A100 生成效果图

打开 `notebooks/qwen_depth_colab.ipynb`，选择 A100 GPU，按顺序运行。Notebook 会安装固定版本的 DiffSynth-Studio，并使用仓库内的示例深度图。首次运行需下载较大模型，建议把 Hugging Face 缓存挂载到 Google Drive。

也可在 GPU 环境命令行运行：

```bash
python inference/generate_qwen_depth.py \
  --depth data/examples/Building-Architecture.depth.png \
  --prompt "当代低层公共建筑，保持原有体量、屋顶轮廓和透视，深灰色清水混凝土，大面积落地玻璃，细黑色金属窗框，专业建筑摄影，阴天柔光，真实材质，周边简洁景观" \
  --output outputs/generated/building.png
```

一次加载模型后批量生成三个基线方案：

```bash
python inference/run_depth_experiment.py \
  --depth data/examples/Building-Architecture.depth.png \
  --config configs/depth_baseline.json \
  --output-dir outputs/depth_baseline
```

仅在本地检查深度图，不加载 GPU 模型：

```bash
.venv/bin/python inference/generate_qwen_depth.py \
  --depth data/examples/Building-Architecture.depth.png \
  --prompt test --validate-only --width 768 --height 768
```

## 当前边界

- 这是“有结构约束的方案表达”，不是可直接施工的工程出图。
- 单视角扩散生成不会自动保证多视角材质完全一致。下一阶段应保存统一的材质规格、seed 和视角元数据，再评估多视图一致性方案。
- 生产使用前需再核对模型权重许可证、客户数据合规与输出审核。

## 模型与运行时

- [Qwen/Qwen-Image](https://huggingface.co/Qwen/Qwen-Image)
- [Qwen-Image Blockwise ControlNet Depth](https://huggingface.co/DiffSynth-Studio/Qwen-Image-Blockwise-ControlNet-Depth)
- [DiffSynth-Studio](https://github.com/modelscope/DiffSynth-Studio)

Colab Notebook 当前固定 DiffSynth-Studio commit `b1c02ce76aabc989f6bf534756b2da84532249e5`，防止上游 API 变化导致突然无法运行。
