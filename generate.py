#!/usr/bin/env python3
"""
ai-video-batch-maker: batch-generate AI videos from a prompt file.

Reads prompts from prompts.txt (one prompt per line) or prompts.json
(per-video options), calls the free pollinations.ai video API, and saves
one MP4 per prompt into the output folder.

Usage:
    python generate.py
    python generate.py --prompts my-prompts.txt --out videos --model veo --duration 8 --aspect 9:16

Requires the environment variable POLLINATIONS_API_KEY (free key, no credit
card needed, at https://enter.pollinations.ai).
"""

import argparse
import json
import os
import sys
import time
import urllib.parse

try:
    import requests
except ImportError:
    print("The 'requests' package is missing. Install it with:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

API_BASE = "https://gen.pollinations.ai/video"
VALID_MODELS = ("wan-fast", "wan", "veo", "seedance-2.0")
VALID_ASPECTS = ("16:9", "9:16")

KEY_HELP = (
    "API key missing or invalid. Get a free key (no credit card needed) at "
    "https://enter.pollinations.ai and set it with:\n"
    "  Windows:   set POLLINATIONS_API_KEY=your_key\n"
    "  Mac/Linux: export POLLINATIONS_API_KEY=your_key"
)


def load_prompts(path, default_model, default_duration, default_aspect):
    """Return a list of dicts: {prompt, model, duration, aspect}."""
    if not os.path.exists(path):
        return None
    items = []
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            prompt = entry.get("prompt", "").strip()
            if not prompt:
                continue
            items.append(
                {
                    "prompt": prompt,
                    "model": entry.get("model", default_model),
                    "duration": int(entry.get("duration", default_duration)),
                    "aspect": entry.get("aspect", default_aspect),
                }
            )
    else:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                items.append(
                    {
                        "prompt": line,
                        "model": default_model,
                        "duration": default_duration,
                        "aspect": default_aspect,
                    }
                )
    return items


def fetch_video(prompt, model, duration, aspect, api_key):
    """Call the pollinations.ai video API and return the response."""
    encoded = urllib.parse.quote(prompt, safe="")
    params = {
        "model": model,
        "duration": duration,
        "aspectRatio": aspect,
    }
    url = f"{API_BASE}/{encoded}?{urllib.parse.urlencode(params)}"
    headers = {"Authorization": f"Bearer {api_key}"}
    return requests.get(url, headers=headers, stream=True, timeout=600)


def download_video(prompt, model, duration, aspect, api_key, out_path, index, total):
    short = (prompt[:57] + "...") if len(prompt) > 60 else prompt
    print(f"[{index}/{total}] generating: {short}")
    for attempt in range(1, 4):
        try:
            response = fetch_video(prompt, model, duration, aspect, api_key)
        except requests.RequestException as exc:
            if attempt < 3:
                wait = attempt * 10
                print(f"  network error ({exc}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  FAILED after 3 attempts: {exc}")
            return False

        if response.status_code == 401:
            print(KEY_HELP)
            sys.exit(2)
        if response.status_code == 429:
            if attempt < 3:
                print("  rate limited, waiting 60s before retry...")
                time.sleep(60)
                continue
            print("  FAILED: still rate limited after retries.")
            return False
        if response.status_code >= 500:
            if attempt < 3:
                wait = attempt * 10
                print(f"  server error {response.status_code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  FAILED: server error {response.status_code} after 3 attempts.")
            return False
        if response.status_code != 200:
            print(f"  FAILED: unexpected status {response.status_code}.")
            return False

        with open(out_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
        print(f"  saved: {out_path}")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Batch-generate AI videos from a prompt file using the free pollinations.ai API."
    )
    parser.add_argument("--prompts", default="prompts.txt", help="Prompt file (.txt or .json).")
    parser.add_argument("--out", default="output", help="Folder to save MP4 files in.")
    parser.add_argument("--model", default="wan-fast",
                        help=f"Video model to use ({', '.join(VALID_MODELS)}).")
    parser.add_argument("--duration", type=int, default=8,
                        help="Clip length in seconds.")
    parser.add_argument("--aspect", default="16:9",
                        help="Aspect ratio, 16:9 or 9:16 (9:16 is for Shorts/Reels/TikTok).")
    args = parser.parse_args()

    if args.model not in VALID_MODELS:
        print(f"Unknown model '{args.model}'. Choose from: {', '.join(VALID_MODELS)}")
        sys.exit(1)
    if args.aspect not in VALID_ASPECTS:
        print(f"Unknown aspect '{args.aspect}'. Choose from: {', '.join(VALID_ASPECTS)}")
        sys.exit(1)

    api_key = os.environ.get("POLLINATIONS_API_KEY")
    if not api_key:
        print(KEY_HELP)
        sys.exit(2)

    # Prefer prompts.json when it exists, otherwise use the --prompts file.
    prompt_file = "prompts.json" if os.path.exists("prompts.json") else args.prompts
    items = load_prompts(prompt_file, args.model, args.duration, args.aspect)
    if items is None:
        print(f"Prompt file not found: {prompt_file}")
        print("Create prompts.txt (one prompt per line) or prompts.json and try again.")
        sys.exit(1)
    if not items:
        print(f"No prompts found in {prompt_file}. Add at least one prompt line.")
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    total = len(items)
    made = 0
    skipped = 0
    failed = 0
    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            manifest = []

    for i, item in enumerate(items, start=1):
        filename = f"video-{i:03d}.mp4"
        out_path = os.path.join(args.out, filename)
        if os.path.exists(out_path):
            print(f"[{i}/{total}] already exists, skipping: {out_path}")
            skipped += 1
            continue
        ok = download_video(item["prompt"], item["model"], item["duration"],
                            item["aspect"], api_key, out_path, i, total)
        if ok:
            made += 1
            manifest.append(
                {
                    "file": filename,
                    "prompt": item["prompt"],
                    "model": item["model"],
                    "duration": item["duration"],
                    "aspect": item["aspect"],
                }
            )
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
        else:
            failed += 1

    print(f"\nDone: {made} created, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
