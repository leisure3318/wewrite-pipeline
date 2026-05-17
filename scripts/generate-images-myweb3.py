#!/usr/bin/env python3
"""Generate wewrite-pipeline images through a myweb3-compatible image API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API_BASE = "https://api.myweb3.cc/v1"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_COVER_SIZE = "1808x768"
DEFAULT_IMAGE_SIZE = "1536x864"
IMAGE_REQUEST_TIMEOUT = 300
RETRYABLE_IMAGE_STATUS_CODES = {500, 502, 503, 504, 524}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class ImageApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(key: str, env_file: dict[str, str], default: str = "") -> str:
    return os.environ.get(key) or env_file.get(key) or default


def normalize_image_size(size: str) -> str:
    raw = size.lower().replace("*", "x").strip()
    if "x" not in raw:
        raise RuntimeError(f"Invalid image size: {size}; use WIDTHxHEIGHT, for example 1088x1088")
    width_text, height_text = raw.split("x", 1)
    width = int(width_text)
    height = int(height_text)
    normalized_width = ((width + 15) // 16) * 16
    normalized_height = ((height + 15) // 16) * 16
    return f"{normalized_width}x{normalized_height}"


def http_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        raise ImageApiError(details or str(exc), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise ImageApiError(str(exc)) from exc


def download_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=IMAGE_REQUEST_TIMEOUT) as response:
        return response.read()


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, ImageApiError):
        return exc.status in RETRYABLE_IMAGE_STATUS_CODES or exc.status is None
    return False


def generate_image(api_base: str, api_key: str, model: str, size: str, prompt: str, retries: int) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("Missing IMAGE_API_KEY or MYWEB3_API_KEY")
    url = f"{api_base.rstrip('/')}/images/generations"
    payload = {"model": model, "prompt": prompt, "n": 1, "size": size}
    headers = {"Authorization": f"Bearer {api_key}"}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return http_json(url, payload=payload, headers=headers, timeout=IMAGE_REQUEST_TIMEOUT)
        except Exception as exc:
            last_error = exc
            if attempt >= retries or not is_retryable_error(exc):
                break
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Image generation failed after {retries + 1} attempt(s): {last_error}")


def save_generated_image(response: dict[str, Any], output: Path) -> Path:
    data = response.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError("Image API response does not contain data[0]")
    item = data[0]
    output.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(item.get("b64_json"), str):
        output.write_bytes(base64.b64decode(item["b64_json"]))
        return output
    if isinstance(item.get("url"), str):
        url = item["url"]
        suffix = Path(urllib.parse.urlparse(url).path).suffix or output.suffix
        resolved_output = output.with_suffix(suffix)
        resolved_output.write_bytes(download_bytes(url))
        return resolved_output
    raise RuntimeError("Image API response has neither b64_json nor url")


def existing_image(path_without_suffix: Path) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = path_without_suffix.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def update_meta(article_dir: Path, **values: Any) -> None:
    meta_path = article_dir / "meta.yaml"
    if not meta_path.exists():
        return
    lines = meta_path.read_text(encoding="utf-8").splitlines()
    rendered = {key: render_yaml_value(value) for key, value in values.items()}
    seen: set[str] = set()
    updated: list[str] = []
    for line in lines:
        key = line.split(":", 1)[0].strip() if ":" in line and not line.startswith((" ", "-")) else ""
        if key in rendered:
            updated.append(f"{key}: {rendered[key]}")
            seen.add(key)
        else:
            updated.append(line)
    for key, value in rendered.items():
        if key not in seen:
            updated.append(f"{key}: {value}")
    meta_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def render_yaml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "null"
    return json.dumps(str(value), ensure_ascii=False)


def prompt_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.md") if path.is_file())


def generate_from_prompt(
    prompt_path: Path,
    output_stem: Path,
    size: str,
    api_base: str,
    api_key: str,
    model: str,
    retries: int,
    force: bool,
) -> Path:
    existing = existing_image(output_stem)
    if existing and not force:
        return existing
    prompt = prompt_path.read_text(encoding="utf-8")
    response = generate_image(api_base, api_key, model, size, prompt, retries)
    return save_generated_image(response, output_stem.with_suffix(".png"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate cover and body images for a wewrite-pipeline article.")
    parser.add_argument("article_dir", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--api-base", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--cover-size", default="")
    parser.add_argument("--image-size", default="")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    article_dir = args.article_dir.expanduser().resolve()
    env_file = read_env_file(args.env_file.expanduser())
    api_base = args.api_base or env_value("IMAGE_API_BASE", env_file, DEFAULT_API_BASE)
    api_key = args.api_key or env_value("IMAGE_API_KEY", env_file) or env_value("MYWEB3_API_KEY", env_file)
    model = args.model or env_value("IMAGE_MODEL", env_file, DEFAULT_MODEL)
    cover_size = normalize_image_size(args.cover_size or env_value("COVER_IMAGE_SIZE", env_file, DEFAULT_COVER_SIZE))
    image_size = normalize_image_size(args.image_size or env_value("ARTICLE_IMAGE_SIZE", env_file, DEFAULT_IMAGE_SIZE))

    cover_prompts = prompt_files(article_dir / "02-cover" / "prompts")
    body_prompts = prompt_files(article_dir / "03-images" / "prompts")
    if not cover_prompts and not body_prompts:
        raise RuntimeError("No prompt files found under 02-cover/prompts or 03-images/prompts")

    results: dict[str, Any] = {
        "article_dir": str(article_dir),
        "image_backend": "myweb3",
        "model": model,
        "cover_size": cover_size,
        "image_size": image_size,
        "cover": None,
        "body_images": [],
    }

    try:
        if cover_prompts:
            cover_path = generate_from_prompt(
                cover_prompts[0],
                article_dir / "02-cover" / "cover",
                cover_size,
                api_base,
                api_key,
                model,
                args.retries,
                args.force,
            )
            results["cover"] = str(cover_path)

        for prompt_path in body_prompts:
            image_path = generate_from_prompt(
                prompt_path,
                article_dir / "03-images" / prompt_path.stem,
                image_size,
                api_base,
                api_key,
                model,
                args.retries,
                args.force,
            )
            results["body_images"].append(str(image_path))

        update_meta(
            article_dir,
            status="images_ready",
            cover_images=bool(results["cover"]),
            body_images=len(results["body_images"]),
            image_backend="myweb3",
            image_model=model,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        update_meta(article_dir, status="image_failed", image_backend="myweb3", image_error=str(exc))
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
