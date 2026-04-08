# skills

本分支新增了 `openclaw-ppt-docs` skill，用于将 `.pptx` 自动转换为按页讲解的 Markdown 文档，并抽取插图到独立图片目录。

## 目录
- `openclaw-ppt-docs/SKILL.md`：Skill 说明与使用方法。
- `openclaw-ppt-docs/scripts/generate_ppt_docs.py`：执行脚本。

## 快速开始
```bash
python3 openclaw-ppt-docs/scripts/generate_ppt_docs.py \
  --pptx ./demo.pptx \
  --output ./out
```
