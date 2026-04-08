---
name: openclaw-ppt-docs
description: 将 .pptx 转换为按页讲解的 Markdown 文档，抽取插图，并可调用 OpenClaw Chat Completions 生成讲解要点。
version: 1.0.0
entrypoint:
  command: python3
  args:
    - openclaw-ppt-docs/scripts/generate_ppt_docs.py
inputs:
  - name: pptx
    type: path
    required: true
    description: 源 .pptx 文件路径（仅支持 .pptx）。
  - name: output
    type: path
    required: true
    description: 输出目录；将生成 slides.md、images/、manifest.json。
  - name: openclaw-endpoint
    type: string
    required: false
    description: OpenClaw Chat Completions 地址，例如 http://localhost:8000/v1/chat/completions。
  - name: openclaw-model
    type: string
    required: false
    description: OpenClaw 模型名称。
  - name: timeout
    type: integer
    required: false
    default: 30
    description: OpenClaw 请求超时（秒）。
outputs:
  - name: slides_md
    path: "{output}/slides.md"
    description: 按页讲解文档。
  - name: images_dir
    path: "{output}/images"
    description: 按页导出的图片目录。
  - name: manifest_json
    path: "{output}/manifest.json"
    description: 结构化元数据（页标题、文本、图片、讲解要点）。
---

# OpenClaw Skill: PPT 讲解文档生成

## 功能
此 Skill 将 `.pptx` 解析为讲解材料：
1. 提取每页文本并自动推断标题。
2. 导出每页引用图片到 `images/slide-{n}/`。
3. 生成 `slides.md`（页面内容、讲解要点、插图说明）。
4. 生成 `manifest.json` 供后续工作流复用。

当同时提供 `--openclaw-endpoint` 与 `--openclaw-model` 时，会调用 OpenClaw 生成 3~5 条讲解要点；若调用失败，自动回退到本地规则生成。

## 适用场景
- 快速将演示稿转为演讲讲稿。
- 为知识库/培训内容自动生成结构化文档。
- 在 OpenClaw Agent 流程中作为“PPT 解析 + 讲解增强”步骤。

## 运行方式
### 基础模式（仅本地规则）
```bash
python3 openclaw-ppt-docs/scripts/generate_ppt_docs.py \
  --pptx ./demo.pptx \
  --output ./out
```

### OpenClaw 增强模式
```bash
python3 openclaw-ppt-docs/scripts/generate_ppt_docs.py \
  --pptx ./demo.pptx \
  --output ./out \
  --openclaw-endpoint http://localhost:8000/v1/chat/completions \
  --openclaw-model your-model
```

## 参数规范
- `--pptx`：必须是存在的 `.pptx` 文件。
- `--output`：输出目录（不存在会自动创建）。
- `--openclaw-endpoint`、`--openclaw-model`：需同时提供才会启用 OpenClaw 增强。
- `--timeout`：默认 30 秒。

## 产物说明
- `slides.md`：按页组织的讲解文档。
- `images/`：导出的图片资源。
- `manifest.json`：每页结构化数据，包含：
  - `index`
  - `title`
  - `paragraphs`
  - `images`
  - `explanation_points`

## 错误处理
- 非法输入（文件不存在或非 `.pptx`）会直接退出。
- OpenClaw 请求失败、超时或返回格式异常时，不中断流程，自动使用本地讲解规则。

## 与 OpenClaw 集成建议
1. 将该 Skill 注册为一个可调用工具（tool），参数映射为脚本 CLI 参数。
2. 在工作流中先调用本 Skill 生成 `manifest.json`，再将结构化数据交由后续 Agent 生成课程稿、QA 或摘要。
3. 对大文件可设置更长 `--timeout` 并在调用层增加任务队列。
