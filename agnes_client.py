"""
Agnes Image 2.1 Flash — API 客户端封装

基于 httpx，正确处理官方文档中的全部字段：
  - 文生图 (txt2img)：model + prompt + size
  - 图生图 (img2img)：extra_body.image = [url 或 data:image/png;base64,...]
  - URL 输出：extra_body.response_format = "url"
  - base64 输出：顶层 return_base64 = True（注意：不放 extra_body）
  - 自定义尺寸 + 超时 60–360s
  - 解析响应：data[].url / data[].b64_json / revised_prompt / created

文档参考：https://agnes-ai.com/doc/agnes-image-21-flash
"""

from __future__ import annotations

import base64
import io
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import httpx
from PIL import Image

API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
# 可选模型（来自 Agnes 文档）
MODEL_21_FLASH = "agnes-image-2.1-flash"
MODEL_20_FLASH = "agnes-image-2.0-flash"
# 全部模型：(模型ID, 显示名) —— 显示名用于 UI 下拉框
MODELS = [
    (MODEL_21_FLASH, "Agnes Image 2.1 Flash（推荐，质量更高）"),
    (MODEL_20_FLASH, "Agnes Image 2.0 Flash（更快）"),
]
MODEL = MODEL_21_FLASH  # 默认模型（向后兼容）
DEFAULT_SIZE = "1024x1024"
# 文档建议 60–360 秒
DEFAULT_TIMEOUT = 180
MIN_TIMEOUT, MAX_TIMEOUT = 60, 360

# 提示词优化用的 LLM（OpenAI 兼容的 chat 接口）
CHAT_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
LLM_MODEL = "agnes-2.0-flash"
LLM_TIMEOUT = 60  # 文本优化通常很快

# 指示 LLM 如何优化提示词的 system prompt
# 关键原则：绝不改变/替换主体，只补充细节；专有名词逐字保留
PROMPT_OPTIMIZER_SYSTEM = (
    "You enhance image prompts for text-to-image models to make them more vivid and effective.\n"
    "STRICT RULES (never violate):\n"
    "1) NEVER change, replace, translate, or substitute the subject. If the user names a "
    "character, person, brand, place, or ANY proper noun, you MUST keep it EXACTLY as written "
    "(copy it verbatim — do not 'correct', paraphrase, or swap it for another character). "
    "Do NOT introduce a different subject than what the user asked for.\n"
    "2) Your ONLY job is to ADD descriptive details AROUND the unchanged subject: appearance, "
    "pose, expression, clothing, background, composition, lighting, color palette, mood, "
    "atmosphere, art style, and quality keywords (e.g. masterpiece, best quality, highly detailed).\n"
    "3) Keep non-English names in their original language, and you may add an English gloss "
    "afterwards if helpful — but never drop the original name.\n"
    "Output ONLY the final prompt as a single line. No quotation marks, no explanations, no preamble."
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class GeneratedImage:
    """单张生成结果。image_bytes 永远有值（无论接口返回 url 还是 b64）。"""
    image_bytes: bytes
    url: str | None = None
    revised_prompt: str | None = None
    width: int = 0
    height: int = 0
    fmt: str = "PNG"
    # 来源信息（便于历史记录溯源）
    source_kind: str = "txt2img"  # txt2img / img2img / variation
    reference_image: str | None = None

    @property
    def size_kb(self) -> float:
        return len(self.image_bytes) / 1024.0

    def pil(self) -> Image.Image:
        return Image.open(io.BytesIO(self.image_bytes))

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.image_bytes)
        return path


@dataclass
class GenerateRequest:
    """一次生成请求的完整参数。"""
    prompt: str
    api_key: str
    size: str = DEFAULT_SIZE
    n: int = 1                       # 一次生成的张数
    mode: str = "txt2img"            # txt2img / img2img / variation
    reference_images: list[str] = field(default_factory=list)  # 文件路径或 URL
    return_base64: bool = True       # True=直接拿 base64；False=走 url 再下载
    timeout: float = DEFAULT_TIMEOUT
    model: str = MODEL               # 使用的模型 ID

    def __post_init__(self):
        if not self.prompt.strip():
            raise ValueError("prompt 不能为空")
        if not self.api_key.strip():
            raise ValueError("api_key 不能为空")
        if self.mode not in ("txt2img", "img2img", "variation"):
            raise ValueError(f"未知 mode: {self.mode}")
        if not (1 <= self.n <= 4):
            raise ValueError("n 必须在 1–4 之间")
        self.timeout = max(MIN_TIMEOUT, min(MAX_TIMEOUT, float(self.timeout)))


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class AgnesAPIError(RuntimeError):
    """API 调用失败时抛出，message 中包含状态码与原始响应。"""
    def __init__(self, message: str, status_code: int | None = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ---------------------------------------------------------------------------
# 图片工具
# ---------------------------------------------------------------------------

def image_to_data_uri(path: str | Path, max_dim: int = 1024) -> str:
    """把本地图片转成 data:image/png;base64,... 的 Data URI。

    Agnes 文档：img2img 的 image 数组元素支持 data URI。
    为控制上传体积，会先把图压到 max_dim 内并转 PNG。
    """
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def parse_size(size: str) -> tuple[int, int]:
    """解析 '1024x1024' -> (1024, 1024)。"""
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except Exception as e:
        raise ValueError(f"无法解析尺寸 '{size}'，期望格式如 '1024x1024'") from e


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

class AgnesClient:
    """Agnes Image API 客户端。线程安全（每次请求独立 httpx 调用）。"""

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.api_key = api_key or ""
        self.timeout = max(MIN_TIMEOUT, min(MAX_TIMEOUT, float(timeout)))

    # ---- 核心请求 ----

    def _build_payload(self, req: GenerateRequest) -> dict:
        """按文档构造请求体。

        关键点（来自官方文档 + 故障排查）：
          - return_base64 是顶层字段（base64 输出时），不能放进 extra_body
          - img2img 的参考图放在 extra_body.image（数组）
          - URL 输出用 extra_body.response_format = "url"
        """
        extra_body: dict = {}
        if not req.return_base64:
            extra_body["response_format"] = "url"

        # 图生图 / 变体：把参考图塞进 extra_body.image
        if req.mode in ("img2img", "variation") and req.reference_images:
            images = []
            for ref in req.reference_images:
                if ref.startswith(("http://", "https://", "data:")):
                    images.append(ref)             # 已是 URL / data URI
                else:
                    images.append(image_to_data_uri(ref))  # 本地文件 -> data URI
            extra_body["image"] = images

        payload: dict = {
            "model": req.model,
            "prompt": req.prompt,
            "size": req.size,
            "n": req.n,
        }
        if req.return_base64:
            payload["return_base64"] = True
        if extra_body:
            payload["extra_body"] = extra_body
        return payload

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, req: GenerateRequest) -> dict:
        payload = self._build_payload(req)
        headers = self._headers()
        try:
            with httpx.Client(timeout=req.timeout, follow_redirects=True) as client:
                resp = client.post(API_URL, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise AgnesAPIError(
                f"请求超时（{req.timeout:.0f}s）。图片生成较慢，可在设置中调高超时。"
            ) from e
        except httpx.HTTPError as e:
            raise AgnesAPIError(f"网络错误：{e}") from e

        body_text = resp.text
        if resp.status_code >= 400:
            # 尽量提取结构化错误信息
            msg = body_text
            try:
                j = resp.json()
                if isinstance(j, dict):
                    err = j.get("error") or j.get("message") or j
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            except Exception:
                pass
            raise AgnesAPIError(
                f"API 返回错误 {resp.status_code}: {msg}",
                status_code=resp.status_code, body=body_text,
            )

        try:
            return resp.json()
        except Exception as e:
            raise AgnesAPIError(f"响应不是合法 JSON: {body_text[:500]}") from e

    # ---- 结果解析 ----

    def _parse_response(self, data: dict, req: GenerateRequest) -> list[GeneratedImage]:
        items = data.get("data") or data.get("images") or []
        if not items:
            raise AgnesAPIError(f"响应中未找到图片数据: {data}")

        revised = data.get("revised_prompt")
        results: list[GeneratedImage] = []
        for item in items:
            url = item.get("url") or item.get("image_url")
            b64 = item.get("b64_json") or item.get("base64")

            if b64:
                img_bytes = base64.b64decode(b64)
            elif url:
                img_bytes = self._download(url, timeout=req.timeout)
            else:
                raise AgnesAPIError(f"无法识别的图片数据格式: {item}")

            # 读取尺寸/格式
            try:
                pil = Image.open(io.BytesIO(img_bytes))
                w, h = pil.size
                fmt = (pil.format or "PNG").upper()
            except Exception:
                w, h, fmt = 0, 0, "PNG"

            results.append(GeneratedImage(
                image_bytes=img_bytes, url=url,
                revised_prompt=item.get("revised_prompt") or revised,
                width=w, height=h, fmt=fmt,
                source_kind=req.mode,
                reference_image=req.reference_images[0] if req.reference_images else None,
            ))
        return results

    def _download(self, url: str, timeout: float) -> bytes:
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as c:
                r = c.get(url, headers={"User-Agent": "agnes-image-tool/2.0"})
                r.raise_for_status()
                return r.content
        except httpx.HTTPError as e:
            raise AgnesAPIError(f"下载图片失败 ({url}): {e}") from e

    # ---- 公开 API ----

    def generate(self, req: GenerateRequest) -> list[GeneratedImage]:
        """执行一次生成，返回 1..n 张结果。"""
        if not self.api_key:
            raise AgnesAPIError("未设置 API Key")
        data = self._post(req)
        return self._parse_response(data, req)

    def generate_simple(self, prompt: str, **kw) -> list[GeneratedImage]:
        """便捷方法：快速文生图。"""
        req = GenerateRequest(prompt=prompt, api_key=self.api_key, **kw)
        return self.generate(req)

    # ---- 提示词优化（LLM）----

    def optimize_prompt(self, prompt: str, timeout: float = LLM_TIMEOUT) -> str:
        """调用 LLM（agnes-2.0-flash）优化提示词，返回优化后的纯文本。

        失败时抛 AgnesAPIError，由调用方决定如何处理。
        """
        if not self.api_key:
            raise AgnesAPIError("未设置 API Key")
        prompt = (prompt or "").strip()
        if not prompt:
            raise AgnesAPIError("提示词为空，无法优化")

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": PROMPT_OPTIMIZER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 300,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.post(CHAT_URL, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise AgnesAPIError(f"优化提示词超时（{timeout:.0f}s）") from e
        except httpx.HTTPError as e:
            raise AgnesAPIError(f"优化提示词网络错误：{e}") from e

        body_text = resp.text
        if resp.status_code >= 400:
            msg = body_text
            try:
                j = resp.json()
                err = j.get("error") or j.get("message") or j
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            except Exception:
                pass
            raise AgnesAPIError(f"优化提示词失败 {resp.status_code}: {msg}",
                                status_code=resp.status_code, body=body_text)

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise AgnesAPIError(f"优化提示词响应解析失败: {body_text[:300]}") from e

        # 清理：去引号、首尾空白，取第一行（LLM 偶尔多嘴）
        content = content.strip().strip('"').strip("'").strip()
        if "\n" in content:
            content = content.split("\n", 1)[0].strip()
        return content


# ---------------------------------------------------------------------------
# CLI 自测入口：python agnes_client.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, os, sys
    p = argparse.ArgumentParser(description="Agnes Image 2.1 Flash 客户端自测")
    p.add_argument("--api-key", "-k", default=os.environ.get("AGNES_API_KEY"))
    p.add_argument("--prompt", "-p", default="a cute corgi astronaut on the moon, cinematic lighting")
    p.add_argument("--size", "-s", default=DEFAULT_SIZE)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--model", "-m", default=MODEL, choices=[m for m, _ in MODELS],
                   help="生成模型")
    p.add_argument("--image", "-i", action="append", default=[], help="img2img 参考图路径/URL")
    p.add_argument("--out", "-o", default="agnes_test.png")
    args = p.parse_args()

    if not args.api_key:
        print("错误：请通过 --api-key 或环境变量 AGNES_API_KEY 提供 API Key")
        sys.exit(1)

    mode = "img2img" if args.image else "txt2img"
    client = AgnesClient(args.api_key)
    req = GenerateRequest(
        prompt=args.prompt, api_key=args.api_key, size=args.size, n=args.n,
        mode=mode, model=args.model, reference_images=args.image,
    )
    print(f"模式: {mode} | 尺寸: {args.size} | 张数: {args.n}")
    print(f"提示词: {args.prompt}")
    print("正在生成...")

    t0 = time.time()
    try:
        results = client.generate(req)
    except AgnesAPIError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)

    print(f"\n[OK] 耗时 {time.time()-t0:.1f}s，生成 {len(results)} 张")
    for i, img in enumerate(results):
        out = args.out if len(results) == 1 else f"{Path(args.out).stem}_{i}{Path(args.out).suffix}"
        img.save(out)
        print(f"  [{i}] {img.width}x{img.height} {img.fmt} {img.size_kb:.1f}KB -> {out}")
        if img.url:
            print(f"       url: {img.url}")
        if img.revised_prompt:
            print(f"       revised: {img.revised_prompt}")
