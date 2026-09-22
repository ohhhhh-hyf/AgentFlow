"""把题库相对路径图片收成可显示地址。优先内嵌 data URI，避免 Gradio 打到本机 404。"""
from __future__ import annotations

import base64
import os
import re
import urllib.error
import urllib.request

_IMG_TAG = re.compile(r"<img\b([^>]*?)/?>", re.I)
_SRC_ATTR = re.compile(r'''src\s*=\s*(['"])(.*?)\1''', re.I)
_MAX_BYTES = 2_000_000
_CACHE: dict[str, tuple[bytes, str]] = {}
_FAILED: set[str] = set()

_STATIC_ZUJUAN = "https://staticzujuan.xkw.com"
_READBOY_RES = "https://contres.readboy.com"
_DEFAULT_BASES = (
    _READBOY_RES,
    _STATIC_ZUJUAN,
    "https://aixue.xkw.com",
    "https://img.xkw.com",
    "https://static.xkw.com",
    "https://file.xkw.com",
    "https://cdn.xkw.com",
)


def asset_bases() -> list[str]:
    bases: list[str] = []
    extra = (os.getenv("EXERCISE_SEARCH_ASSET_BASE") or "").strip().rstrip("/")
    if extra:
        bases.append(extra)
    for item in _DEFAULT_BASES:
        if item not in bases:
            bases.append(item)
    return bases


def absolute_src(src: str) -> str:
    text = (src or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://", "data:")):
        return text
    if text.startswith("//"):
        return "https:" + text
    if not text.startswith("/"):
        text = "/" + text
    # 组卷公式图：相对 /quesimg/... 就在这个 CDN 上
    if text.startswith("/quesimg/"):
        return _STATIC_ZUJUAN + text
    # 爱学试卷图：/resources/aixue_paper/... 在 contres.readboy.com
    if text.startswith("/resources/"):
        return _READBOY_RES + text
    bases = asset_bases()
    return (bases[0] if bases else _READBOY_RES) + text


def _candidate_urls(src: str) -> list[str]:
    text = (src or "").strip()
    if text.startswith(("http://", "https://")):
        return [text]
    if text.startswith("//"):
        return ["https:" + text]
    path = text if text.startswith("/") else "/" + text
    urls: list[str] = []
    tails = [path]
    if path.startswith("/resources/"):
        tails.append(path[len("/resources") :])
        tails.append("/dksihd" + path)
        tails.append("/dksihd" + path[len("/resources") :])
    for base in asset_bases():
        for tail in tails:
            urls.append(base + tail)
    return list(dict.fromkeys(urls))


def _get(url: str) -> tuple[bytes, str] | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://contres.readboy.com/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = resp.read(_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if len(data) > _MAX_BYTES or not data:
        return None
    if not mime.startswith("image/"):
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif data[:2] == b"\xff\xd8":
            mime = "image/jpeg"
        elif data[:6] in {b"GIF87a", b"GIF89a"}:
            mime = "image/gif"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            return None
    return data, mime


def fetch_image(src: str) -> tuple[bytes, str] | None:
    key = (src or "").strip()
    if not key or key in _FAILED:
        return None
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    for url in _candidate_urls(key):
        got = _get(url)
        if got is None:
            continue
        _CACHE[key] = got
        return got
    _FAILED.add(key)
    return None


def data_uri(src: str) -> str:
    got = fetch_image(src)
    if got is None:
        return absolute_src(src)
    data, mime = got
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def rewrite_images(raw: object) -> str:
    """题干/解析里的 <img>：相对路径改绝对或内嵌，公式图和配图都能显示。"""
    text = str(raw or "")
    if "<img" not in text.lower():
        return text

    def _one(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        src_hit = _SRC_ATTR.search(attrs)
        src = src_hit.group(2).strip() if src_hit else ""
        if not src:
            return match.group(0)
        resolved = data_uri(src)
        kind = "quiz-formula" if "formula" in src.lower() else "quiz-figure"
        if not resolved.startswith(("data:", "http://", "https://")):
            return ""
        if src_hit:
            attrs = (
                attrs[: src_hit.start()]
                + f'src="{resolved}"'
                + attrs[src_hit.end() :]
            )
        else:
            attrs += f' src="{resolved}"'
        if re.search(r"\bclass\s*=", attrs, re.I):
            attrs = re.sub(
                r'''class\s*=\s*(['"])([^'"]*)\1''',
                lambda m: f'class="{m.group(2)} {kind}"',
                attrs,
                count=1,
                flags=re.I,
            )
        else:
            attrs += f' class="{kind}"'
        if kind == "quiz-figure" and "style=" not in attrs.lower():
            attrs += ' style="display:block;max-width:100%;height:auto;margin:8px 0"'
        if kind == "quiz-formula" and "style=" not in attrs.lower():
            attrs += ' style="vertical-align:middle"'
        return f"<img{attrs}>"

    return _IMG_TAG.sub(_one, text)


__all__ = [
    "absolute_src",
    "asset_bases",
    "data_uri",
    "fetch_image",
    "rewrite_images",
]
