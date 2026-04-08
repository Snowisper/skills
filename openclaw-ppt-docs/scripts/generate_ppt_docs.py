#!/usr/bin/env python3
"""Generate markdown speaker notes from a .pptx file.

Features:
- Reads slides text from OpenXML structure.
- Extracts referenced images into an images directory.
- Creates slides.md with per-slide explanation sections.
- Optionally uses an OpenClaw-compatible chat completion endpoint to enhance notes.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
import zipfile

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass
class PictureRef:
    rel_id: str
    name: str
    descr: str


@dataclass
class SlideData:
    index: int
    title: str
    paragraphs: list[str]
    images: list[str]
    explanation_points: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PPT explanation markdown.")
    parser.add_argument("--pptx", required=True, help="Path to source .pptx")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--openclaw-endpoint", default="", help="Optional OpenClaw chat completion endpoint")
    parser.add_argument("--openclaw-model", default="", help="Optional model name for OpenClaw")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds for OpenClaw calls")
    return parser.parse_args()


def sanitize_filename(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return base or "image"


def read_xml(zf: zipfile.ZipFile, path: str) -> ET.Element:
    data = zf.read(path)
    return ET.fromstring(data)


def get_slide_paths(zf: zipfile.ZipFile) -> list[str]:
    slides = [name for name in zf.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
    slides.sort(key=lambda p: int(re.search(r"slide(\d+)\.xml$", p).group(1)))
    return slides


def extract_text_paragraphs(slide_root: ET.Element) -> list[str]:
    paragraphs: list[str] = []
    for para in slide_root.findall(".//a:p", NS):
        runs = [node.text or "" for node in para.findall(".//a:t", NS)]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def infer_title(paragraphs: list[str], slide_index: int) -> str:
    if paragraphs:
        candidate = paragraphs[0].strip()
        if candidate:
            return candidate
    return f"Slide {slide_index}"


def parse_relationships(zf: zipfile.ZipFile, slide_path: str) -> dict[str, str]:
    rels_path = slide_path.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
    if rels_path not in zf.namelist():
        return {}

    root = read_xml(zf, rels_path)
    rels: dict[str, str] = {}
    for rel in root.findall(".//{*}Relationship"):
        rid = rel.attrib.get("Id", "")
        target = rel.attrib.get("Target", "")
        if rid and target:
            if target.startswith("../"):
                target = "ppt/" + target[3:]
            elif target.startswith("/"):
                target = target.lstrip("/")
            else:
                target = "ppt/slides/" + target
            rels[rid] = target
    return rels


def extract_picture_refs(slide_root: ET.Element) -> list[PictureRef]:
    refs: list[PictureRef] = []
    for pic in slide_root.findall(".//p:pic", NS):
        blip = pic.find(".//a:blip", NS)
        if blip is None:
            continue
        rid = blip.attrib.get(f"{{{NS['r']}}}embed", "")
        nvpr = pic.find(".//p:cNvPr", NS)
        name = nvpr.attrib.get("name", "") if nvpr is not None else ""
        descr = nvpr.attrib.get("descr", "") if nvpr is not None else ""
        if rid:
            refs.append(PictureRef(rel_id=rid, name=name, descr=descr))
    return refs


def local_explanation(paragraphs: list[str], images: list[str]) -> list[str]:
    body = [p for p in paragraphs[1:4]] or paragraphs[:3]
    points: list[str] = []
    if body:
        points.append(f"先概述本页核心信息：{body[0]}")
    if len(body) > 1:
        points.append(f"补充背景/逻辑递进：{body[1]}")
    if images:
        points.append(f"本页包含 {len(images)} 张插图，讲解时先交代图中对象，再解释与主题关系。")
    points.append("结尾可给出本页的结论或过渡到下一页的问题。")
    return points


def call_openclaw(endpoint: str, model: str, timeout: int, title: str, paragraphs: list[str], images: list[str]) -> list[str]:
    prompt = {
        "title": title,
        "paragraphs": paragraphs,
        "images": images,
        "task": "请输出3-5条中文讲解要点，每条不超过50字，聚焦演讲者讲述顺序。",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是演示文稿讲解助手。"},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0.3,
    }

    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenClaw request failed: {exc}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenClaw response format invalid") from exc

    lines = []
    for raw in str(content).splitlines():
        line = raw.strip().lstrip("-•0123456789. ")
        if line:
            lines.append(line)
    return lines[:5]


def extract_images_for_slide(
    zf: zipfile.ZipFile,
    slide_index: int,
    slide_path: str,
    output_images_root: Path,
) -> list[str]:
    slide_root = read_xml(zf, slide_path)
    rel_map = parse_relationships(zf, slide_path)
    pic_refs = extract_picture_refs(slide_root)

    saved_paths: list[str] = []
    slide_dir = output_images_root / f"slide-{slide_index}"
    slide_dir.mkdir(parents=True, exist_ok=True)

    for img_idx, ref in enumerate(pic_refs, start=1):
        target = rel_map.get(ref.rel_id)
        if not target or target not in zf.namelist():
            continue

        ext = Path(target).suffix or ".bin"
        base_name = sanitize_filename(ref.name or f"image-{img_idx}")
        out_name = f"{img_idx:02d}-{base_name}{ext}"
        out_path = slide_dir / out_name
        out_path.write_bytes(zf.read(target))
        saved_paths.append(str(out_path.relative_to(output_images_root.parent)).replace("\\", "/"))

    return saved_paths


def build_markdown(slides: list[SlideData]) -> str:
    lines = ["# PPT 讲解文档", ""]
    for slide in slides:
        lines.append(f"## 第 {slide.index} 页：{slide.title}")
        lines.append("")

        lines.append("### 页面内容")
        if slide.paragraphs:
            for p in slide.paragraphs:
                lines.append(f"- {p}")
        else:
            lines.append("- （本页未提取到文本内容）")
        lines.append("")

        lines.append("### 讲解要点")
        for point in slide.explanation_points:
            lines.append(f"- {point}")
        lines.append("")

        lines.append("### 插图说明")
        if slide.images:
            for img in slide.images:
                lines.append(f"- ![]({img})")
                lines.append("  - 建议说明：描述图中关键元素、数据趋势与结论。")
        else:
            lines.append("- 本页无插图")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    pptx_path = Path(args.pptx).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()
    images_root = output_root / "images"

    output_root.mkdir(parents=True, exist_ok=True)
    images_root.mkdir(parents=True, exist_ok=True)

    if not pptx_path.exists() or pptx_path.suffix.lower() != ".pptx":
        raise SystemExit("--pptx 必须是存在的 .pptx 文件")

    slides: list[SlideData] = []

    with zipfile.ZipFile(pptx_path, "r") as zf:
        for idx, slide_path in enumerate(get_slide_paths(zf), start=1):
            slide_root = read_xml(zf, slide_path)
            paragraphs = extract_text_paragraphs(slide_root)
            title = infer_title(paragraphs, idx)
            images = extract_images_for_slide(zf, idx, slide_path, images_root)

            if args.openclaw_endpoint and args.openclaw_model:
                try:
                    points = call_openclaw(
                        endpoint=args.openclaw_endpoint,
                        model=args.openclaw_model,
                        timeout=args.timeout,
                        title=title,
                        paragraphs=paragraphs,
                        images=images,
                    )
                    if not points:
                        points = local_explanation(paragraphs, images)
                except RuntimeError:
                    points = local_explanation(paragraphs, images)
            else:
                points = local_explanation(paragraphs, images)

            slides.append(
                SlideData(
                    index=idx,
                    title=title,
                    paragraphs=paragraphs,
                    images=images,
                    explanation_points=points,
                )
            )

    markdown = build_markdown(slides)
    (output_root / "slides.md").write_text(markdown, encoding="utf-8")

    manifest = {
        "source": str(pptx_path),
        "slides_count": len(slides),
        "slides": [
            {
                "index": s.index,
                "title": s.title,
                "paragraphs": s.paragraphs,
                "images": s.images,
                "explanation_points": s.explanation_points,
            }
            for s in slides
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Generated: {(output_root / 'slides.md')}")
    print(f"Images dir: {images_root}")
    print(f"Manifest: {(output_root / 'manifest.json')}")


if __name__ == "__main__":
    main()
