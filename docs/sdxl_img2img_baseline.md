# SDXL 建筑材质增强基线：原理与实验方法

## 1. 我们实际解决的任务

输入不是空白深度图，也不是让 AI 重新设计建筑，而是设计师已经完成的 SketchUp/Blender 场景渲染：

```text
已有几何 + 已有材质分区 + 已有环境 + 固定相机
                     ↓
             SDXL 低强度 Img2Img
                     ↓
材质质感、反射、光影和整体真实感得到增强的汇报效果图
```

第一阶段只输入基础材质 RGB 和提示词，是为了测量 SDXL 自身的增强能力。Depth、Canny、遮罩和 LoRA 会在后续作为独立变量逐步加入。

## 2. SDXL Img2Img 内部发生了什么

### 2.1 VAE 将输入图压缩到潜空间

输入图片 `x` 先经过 SDXL 的 VAE Encoder，得到潜变量 `z₀`：

```text
1024×768×3 RGB → VAE Encoder → 128×96×4 latent
```

扩散过程在这个较小的 latent 上运行，因此计算量远低于直接处理所有 RGB 像素。VAE 负责表示图像，而不是负责逐步生成。

### 2.2 strength 决定添加多少噪声

Img2Img 不从纯随机噪声出发，而是向输入 latent 添加一定程度的噪声：

```text
z₀ + strength 对应的噪声 → zₜ
```

- strength 越低：保留原图越多，增强空间越小。
- strength 越高：模型重绘自由度越大，真实感可能更强，设计漂移风险也更高。

当 `num_inference_steps=50` 时，三档实验大致使用：

| strength | 近似实际去噪步数 | 预期 |
|---:|---:|---|
| 0.15 | 7–8 | 最保守，主要调整色调和局部质感 |
| 0.25 | 12–13 | 真实感与结构保持之间的候选平衡点 |
| 0.35 | 17–18 | 增强明显，但构件变化风险提高 |

这里的50是调度器的完整时间轴长度，并不意味着 strength 0.15 会执行完整50步。

### 2.3 文本编码器告诉模型“向哪里增强”

SDXL 使用两套冻结的 CLIP 文本编码器。提示词被转换为语义向量，随后通过 Cross Attention 影响 UNet 去噪。

我们的提示词只描述：

- PBR 材质；
- 金属、玻璃和自然反射；
- 全局光照和柔和阴影；
- 建筑可视化和甲方汇报质感。

不重复描述建筑类型、体块和环境布局，避免模型把已有设计重新解释一遍。

### 2.4 UNet 逐步预测噪声

SDXL 的 UNet 接收：

```text
当前含噪 latent + 当前时间步 + 文本条件
```

它反复预测并移除噪声，最后得到增强后的 latent。VAE Decoder 再将其解码回 RGB 图像。

## 3. 配置文件为什么要独立

配置位于 `configs/sdxl_img2img_baseline.json`，分为六组：

### model

- `id`：Hugging Face 模型 ID。
- `variant=fp16`：下载半精度权重，节省存储和显存。
- `dtype=float16`：A100 推理使用 FP16。
- `use_safetensors`：只使用安全权重格式。

### input

- `image`：基础材质图路径。
- `width/height`：模型实际处理尺寸。
- `resize_mode=cover`：保持比例后居中裁剪；不会像 stretch 一样拉伸建筑。

最好从 Blender 直接输出目标比例，避免任何裁剪。

### prompt / negative_prompt

正面提示词定义渲染品质，负面提示词抑制重新设计、构件变形、文字与水印。负面提示词不是硬规则，只是概率引导。

### inference

- `seed`：固定随机起点，便于公平比较。
- `num_inference_steps`：完整扩散时间轴长度。
- `guidance_scale`：文本引导强度；太高会压过输入图。
- `scheduler`：当前使用 DPM++ 2M Karras。
- `strengths`：同一次模型加载依次生成三档结果。

### runtime

- A100 40GB 直接使用 CUDA，无需 CPU offload。
- VAE slicing 可以降低 VAE 峰值显存。

### output

结果、输入副本和完整运行元数据写入 Google Drive。以后每张结果都能追溯模型、Seed、提示词和参数。

## 4. 如何判断第一轮结果

不要只看“哪张漂亮”，而要同时记录以下指标：

| 指标 | 检查内容 |
|---|---|
| 几何一致性 | 主梁、拱架、玻璃筒和相机是否变化 |
| 材质提升 | 金属、玻璃、地面是否更真实 |
| 光照统一 | 主光方向、阴影和反射是否自洽 |
| 幻觉 | 是否新增树木、文字、构件或入口 |
| 可交付性 | 是否接近甲方汇报图，而不只是风格滤镜 |

基线决策：

- 0.15 已足够：优先保持低强度，后续只增加高分辨率处理。
- 0.25 最平衡：将其作为下一轮 Canny 实验的基准。
- 0.35 才有明显提升但结构漂移：必须加入 Canny/Depth 或局部遮罩。
- 三档都只是调色：更换建筑领域 Checkpoint/LoRA，或增加专门的材质与光照条件。

## 5. 下一阶段如何扩展

按单变量实验推进：

```text
阶段A：RGB + Prompt
阶段B：RGB + Prompt + Canny
阶段C：RGB + Prompt + Canny + Depth
阶段D：Material/Object ID 遮罩 + 局部增强
阶段E：高分辨率分块处理
```

### Canny

锁定可见边缘、杆件、门窗和分缝。它比 Depth 更适合保护细部，但不能表达前后距离。

### Depth

锁定体块、空间前后和相机透视。它不能单独锁定材质或所有细线构件。

### Object/Material ID

把“允许 AI 修改哪些区域”变成确定规则。例如建筑主体低强度增强，天空和远景允许更高强度生成。

## 6. 数据与训练的关系

第一版不训练。SDXL 已经学习过通用材质、光照和建筑摄影先验，我们先测量预训练能力上限。

只有出现稳定、可复现的缺陷时才训练：

- 总是缺少建筑表现感：训练建筑效果图 LoRA。
- 总是改变细部：微调建筑 Canny/Depth ControlNet。
- 总是丢失原始材质：加入参考图 Adapter 或训练低清渲染到 PBR 渲染的轻量模块。

训练的目标不是让模型重新设计，而是提高“增强真实感且服从已有方案”的概率。

## 7. 复现实验

Colab 使用：

```text
notebooks/sdxl_img2img_baseline_colab.ipynb
```

Notebook 与旧版 Qwen 实验共用以下持久化缓存目录：

```text
MyDrive/ifc-ai-render-cache/huggingface
```

不要随意更改 `CACHE_DIR`，否则 Hugging Face 会在新目录重新下载一份权重。不同模型仍会分别占用空间；共用缓存目录并不代表 Qwen 权重可以替代 SDXL 权重。

命令行校验配置但不下载模型：

```bash
.venv/bin/python inference/generate_sdxl_img2img.py \
  --config configs/sdxl_img2img_baseline.json \
  --validate-only
```

GPU 环境运行：

```bash
python inference/generate_sdxl_img2img.py \
  --config configs/sdxl_img2img_baseline.json \
  --cache-dir /path/to/huggingface-cache
```
