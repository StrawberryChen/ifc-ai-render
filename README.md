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

打开 `notebooks/qwen_depth_colab.ipynb`，选择 A100 GPU，按顺序运行。Notebook 会安装固定版本的 DiffSynth-Studio，并使用仓库内的示例深度图。Notebook 默认挂载 Google Drive，将 Hugging Face 和 ModelScope 的模型缓存持久化到 `MyDrive/ifc-ai-render-cache/`，避免 Colab 运行时释放后重新下载。首次仍需下载较大模型。

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

## 3. fal.ai FLUX Depth API（MVP推荐）

该路线不下载模型权重，也不需要本地GPU。在 [fal.ai](https://fal.ai/models/fal-ai/flux-control-lora-depth/api) 创建 API Key，然后在终端临时设置（不要写入代码或提交到Git）：

```bash
export FAL_KEY="your-key"
.venv/bin/pip install -r requirements-api.txt
.venv/bin/python inference/generate_flux_depth_api.py \
  --depth data/examples/Building-Architecture.depth.png \
  --prompt "photorealistic contemporary public architecture, preserve the exact massing, roofline and camera perspective from the depth map, warm white stone facade, dark metal window frames, low-reflection glazing, professional architectural visualization, soft daylight" \
  --output outputs/fal_flux_depth/daylight.png
```

本地只验证深度预处理和请求参数，不消耗API额度：

```bash
.venv/bin/python inference/generate_flux_depth_api.py \
  --depth data/examples/Building-Architecture.depth.png \
  --prompt test --validate-only
```

脚本会保存生成图、实际上传的8位深度控制图和JSON请求/响应记录。由于输入本身已是Blender深度图，请求固定使用 `preprocess_depth=false`。

## SDCC 有材质建筑样例

`data/sdcc` 是公共领域的 San Diego Convention Center 风格 OBJ 样例。直接生成彼此像素对齐的基础材质图、连续深度图、边缘图和建筑遮罩：

```bash
python3 scripts/build_sdcc_scene.py
```

输出位于 `outputs/sdcc/`：

- `sdcc.material.png`：SDXL Img2Img 主输入
- `sdcc.depth.png`：16位连续深度，近处为白色
- `sdcc.edge.png`：门窗和构件边缘条件
- `sdcc.building_mask.png`：保护主体建筑的遮罩
- `sdcc.scene.blend`：可继续调整相机、材质和灯光的 Blender 场景

## SDXL Img2Img 材质增强基线

第一轮只使用基础材质 RGB 与提示词，对比 `strength=0.15/0.25/0.35`：

- Colab：`notebooks/sdxl_img2img_baseline_colab.ipynb`
- 配置：`configs/sdxl_img2img_baseline.json`
- 推理：`inference/generate_sdxl_img2img.py`
- 原理说明：`docs/sdxl_img2img_baseline.md`

只校验配置和输入，不加载模型：

```bash
.venv/bin/python inference/generate_sdxl_img2img.py \
  --config configs/sdxl_img2img_baseline.json \
  --validate-only
```

## SDXL + Canny ControlNet

在基础材质图之外输入像素对齐的边缘图，用预训练 Canny ControlNet 约束钢梁、屋面和玻璃轮廓，无需先训练：

- Colab：`notebooks/sdxl_canny_img2img_colab.ipynb`
- 配置：`configs/sdxl_canny_img2img.json`
- ControlNet：`diffusers/controlnet-canny-sdxl-1.0`

模型和 SDXL 共用 Drive 缓存 `MyDrive/ifc-ai-render-cache/huggingface`。第一次运行只会新增下载 ControlNet 权重。

```bash
.venv/bin/python inference/generate_sdxl_img2img.py \
  --config configs/sdxl_canny_img2img.json \
  --validate-only
```

## 两阶段完整场景生成

当原始模型只有空白地面时，先使用反向建筑遮罩只生成建筑以外的铺装、道路与景观，再通过 Canny 低强度统一整张图：

- Colab：`notebooks/sdxl_scene_two_stage_colab.ipynb`
- 配置：`configs/sdxl_scene_two_stage.json`
- 推理：`inference/generate_sdxl_scene_two_stage.py`
- 场景模型：`diffusers/stable-diffusion-xl-1.0-inpainting-0.1`

```bash
.venv/bin/python inference/generate_sdxl_scene_two_stage.py \
  --config configs/sdxl_scene_two_stage.json \
  --validate-only
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
