# OpenClaw PPT 讲解文档生成 Skill

## 用途
将一个 `.pptx` 文件转换为结构化的讲解文档：
- 逐页读取 slide 文本内容。
- 导出每页中使用的插图到独立图片目录。
- 生成 Markdown 说明文档，包含每页摘要、讲解要点与图片说明占位。

该 Skill 适合在需要快速为演示文稿产出“讲稿/解说文档”时使用。

---

## 输入与输出

### 输入
- `pptx_path`：要处理的 PowerPoint 文件路径。
- `output_dir`：输出目录。
- `openclaw_endpoint`（可选）：OpenClaw 服务地址（例如 `http://localhost:8000/v1/chat/completions`）。
- `openclaw_model`（可选）：OpenClaw 使用的模型名。

### 输出
在 `output_dir` 下生成：
- `slides.md`：完整讲解文档（Markdown）。
- `images/`：从 PPT 提取出的图片文件。
- `manifest.json`：每页文本、图片映射和生成元数据，便于后续流程复用。

---

## 工作流
1. 解析 `.pptx` 内部结构（OpenXML）。
2. 遍历每一页，抽取文本块与图片关系。
3. 导出图片资源到 `images/slide-{n}/`。
4. 生成每页 Markdown：
   - 页面标题（自动推断）
   - 页面正文摘要
   - 讲解要点（可选由 OpenClaw 增强）
   - 插图清单与说明占位
5. 汇总所有页面生成 `slides.md`。

---

## 使用方式

### 快速命令
```bash
python3 openclaw-ppt-docs/scripts/generate_ppt_docs.py \
  --pptx ./demo.pptx \
  --output ./out
```

### 启用 OpenClaw 增强讲解
```bash
python3 openclaw-ppt-docs/scripts/generate_ppt_docs.py \
  --pptx ./demo.pptx \
  --output ./out \
  --openclaw-endpoint http://localhost:8000/v1/chat/completions \
  --openclaw-model your-model
```

---

## 说明
- 若未提供 OpenClaw 参数，脚本会使用本地规则生成“讲解要点”。
- 当前支持 `.pptx`（不支持旧版 `.ppt`）。
- 图片说明会先生成结构化占位文本，可由你后续补充或二次调用视觉模型增强。
