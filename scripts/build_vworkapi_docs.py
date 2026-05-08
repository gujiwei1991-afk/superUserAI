#!/usr/bin/env python3
"""Convert the raw ShowDoc JSON dump into per-category Markdown files
under docs/vworkapi/.

Source: vwork-docs-raw.json (a flat dict of page_id -> ShowDoc page record).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "vwork-docs-raw.json"
OUT_DIR = ROOT / "docs" / "vworkapi"

# cat_id -> (slug, title, sort_order)
CATEGORIES = {
    "5561945": ("01-basic", "1、基础功能", 1),
    "5561946": ("02-list", "2、好友/群/成员/公司/部门 列表", 2),
    "5561947": ("03-send", "3、发送消息", 3),
    "5561948": ("04-friend", "4、好友操作", 4),
    "5561949": ("05-group", "5、群操作", 5),
    "5561950": ("06-tag", "6、标签操作", 6),
    "5561951": ("07-control", "7、控制类", 7),
    "5561952": ("08-open-platform", "8、开放平台", 8),
    "5561953": ("09-cdn", "9、CDN 上下载", 9),
    "5561954": ("10-misc", "10、其他", 10),
    "5561955": ("11-recv", "消息推送（DLL 主动请求你的）", 11),
}
# Pages without cat_id (top-level docs)
TOP_LEVEL = {
    "10976057765422043": ("说明", 0),
    "10976057897406862": ("社区版跟专业版的区别", 0),
}


def decode(content: str) -> str:
    """ShowDoc returns content with HTML-encoded quotes. Restore them."""
    return html.unescape(content or "").replace("\r\n", "\n").rstrip() + "\n"


def main() -> None:
    text = RAW.read_text(encoding="utf-8")
    raw = json.loads(text)
    # Playwright stored a JSON-stringified value, so we may need to decode twice.
    if isinstance(raw, str):
        raw = json.loads(raw)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict]] = {}
    untouched: list[dict] = []
    for page_id, rec in raw.items():
        if not isinstance(rec, dict) or "page_content" not in rec:
            continue
        cat_id = str(rec.get("cat_id", "")).strip()
        if cat_id and cat_id in CATEGORIES:
            grouped.setdefault(cat_id, []).append(rec)
        else:
            untouched.append(rec)

    # Write per-category file
    for cat_id, (slug, title, _order) in CATEGORIES.items():
        pages = grouped.get(cat_id, [])
        # Sort by s_number then title
        pages.sort(key=lambda r: (int(r.get("s_number", "0") or "0"), r.get("page_title", "")))
        path = OUT_DIR / f"{slug}.md"
        with path.open("w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"> 来源: showdoc.com.cn/mrsanshui (cat_id={cat_id})\n\n")
            for p in pages:
                pid = p.get("page_id", "")
                pt = p.get("page_title", "untitled")
                f.write(f"## {pt}\n\n")
                f.write(f"页面 ID: `{pid}` · 链接: https://www.showdoc.com.cn/mrsanshui/{pid}\n\n")
                f.write(decode(p.get("page_content", "")))
                f.write("\n---\n\n")
        print(f"wrote {path.relative_to(ROOT)} ({len(pages)} pages)")

    # Top-level / overview file
    overview_path = OUT_DIR / "00-overview.md"
    with overview_path.open("w", encoding="utf-8") as f:
        f.write("# vworkApi 文档归档（本地缓存）\n\n")
        f.write("> 来源: https://www.showdoc.com.cn/mrsanshui/10976057765422043 \n")
        f.write("> 抓取时间: 见 git 提交;后续接口字段如有改动请重新抓取。\n\n")
        f.write("## 章节速查\n\n")
        for cat_id, (slug, title, _order) in CATEGORIES.items():
            f.write(f"- [{title}](./{slug}.md)\n")
        f.write("\n## 关键决策（本项目）\n\n")
        f.write("- **入站消息字段判定**(见 `11-recv.md` → 聊天消息):\n")
        f.write("  - `sender != ''` ⇒ 群消息(此时 `user_id` 是群 ID,`sender` 是发送者 ID)\n")
        f.write("  - `sender == ''` ⇒ 私聊(此时 `user_id` 就是发送者 ID)\n")
        f.write("  - `self_user_id in at_list` 或 `'notify@all' in at_list` ⇒ 被 @ 到\n")
        f.write("- **发送文本到群**: 直接用 `type=3000` SEND_TEXT,`user_id=群ID`(见 `03-send.md` → 发送文本消息)\n")
        f.write("- **发送 @ 群成员**: `type=3009` SEND_AT_GROUP,字段 `chat_room_id`/`at_list`/`msg`(见 `03-send.md` → 群聊发送消息并且@指定群成员)\n\n")
        f.write("## 顶层说明\n\n")
        for p in untouched:
            for tid, (ttitle, _o) in TOP_LEVEL.items():
                if str(p.get("page_id")) == tid:
                    f.write(f"### {ttitle}\n\n")
                    f.write(decode(p.get("page_content", "")))
                    f.write("\n---\n\n")
    print(f"wrote {overview_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
