# IFC AI Render Core Asset Library

该目录是 Blender Executor 的稳定资产接口，不是随意存放模型的文件夹。

- `registry/asset_registry.json`：唯一资产索引；Executor通过 `asset_id` 查找文件和数据块。
- `presets/`：将项目语义类型映射到材质和对象池。
- `library/`：由 `blender/build_core_asset_library.py` 生成的Blend资产库。
- `licenses/`：每个资产必须引用可追踪的许可证记录。

构建：

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  -b --python blender/build_core_asset_library.py -- \
  --output-dir assets/library
```

第一版资产均由代码使用Blender基础几何和程序化材质生成，不包含第三方模型或贴图。它们用于验证自动加载、材质映射、散布和LOD接口，不代表最终交付品质。

Blender执行器统一通过 `blender/asset_library.py` 按 `asset_id` 加载材质或Collection，不直接硬编码Blend文件中的数据块名称。验证所有注册资产均可加载：

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  -b --python blender/smoke_test_asset_library.py -- \
  --registry assets/registry/asset_registry.json \
  --report outputs/assets/core_asset_smoke_report.json
```
