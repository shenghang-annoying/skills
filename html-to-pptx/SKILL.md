---
name: html-to-pptx
description: Convert HTML slide decks to editable native-element PPTX files. Use when the user asks to 转成 PPTX / convert HTML to PowerPoint and requires editable slides. Do not use for screenshot-image PPTX or for editing existing .pptx files.
---

# HTML → PPTX（可编辑）

用 PyPI 的 `html-to-pptx`（v0.4.x）把 HTML 幻灯片转成**原生元素** PPTX（文本框/形状/渐变均可编辑）。禁止走「整页截图」路线——产出全是图片，用户明确拒绝过。

## 环境准备

```sh
pip install html-to-pptx        # 联动安装 python-pptx / playwright / lxml / pillow
python -m playwright install chromium
```

## 操作流程

1. 运行 `python scripts/html2pptx.py <input.html> <output.pptx>`（脚本自动处理下面两个坑）。
2. 用 PowerPoint/WPS 打开验证：内容应铺满整个 16:9 画布、文本可选中编辑。
3. 若发现局部样式异常（SVG 装饰、canvas、复杂滤镜），那是库把该元素栅格化成了背景图——属预期降级，文字仍是原生的。

## 两个必踩的坑（脚本已内置处理，手动转时必须知道）

1. **内容只占画布 2/3**：源页面常用「1280×720 固定舞台 + `transform: scale()` 响应式缩放」。该库画布固定 1920×1080，测量前会**清除祖先 transform**（layout 空间回到 1280×720），导致内容映射后只占 2/3。解法：给舞台元素注入 `zoom: 1.5`（1920/1280）——zoom 不属于 transform，不会被清除，测量空间即变成 1920×1080。
2. **Google Fonts 等外链字体导致挂起**：页面加载等 `networkidle` 会因外链超时卡死。转之前移除外链字体 `<link>`，用系统字体兜底。

## 约束与边界

- 幻灯片结构要求：每页为 `<section class="slide">`（或 reveal.js section）；不支持 JS 动态生成且无法静态测量的内容。
- SVG/canvas/WebP、径向/锥形渐变、复杂滤镜会被栅格化为背景图压在原生文本之下。
- 讲者备注：`data-pptx-notes` 属性或 reveal.js `<aside class="notes">` 会带入 PPTX 备注。
