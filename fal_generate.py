#!/usr/bin/env python3
"""
ai-video-batch-maker (fal.ai cloud backend): batch-generate AI videos
from a prompt file using fast cloud GPUs. No local GPU needed.

Reads prompts from prompts.txt (one prompt per line) or prompts.json
(per-video options), submits each prompt to the fal.ai queue API, waits
for the cloud render, and saves one MP4 per prompt into the output
folder.

Usage:
    python fal_generate.py
    python fal_generate.py --model veo --duration 8 --aspect 9:16
    python fal_generate.py --prompts my-prompts.txt --out videos

Requires the environment variable FAL_KEY (create a key at
https://fal.ai/dashboard/keys and add a small prepaid credit balance at
https://fal.ai/dashboard/billing). Billing is pay per second of video:
Wan is the cheap fast option, Veo 3.1 is Google's Flow model.

Uses only the Python standard library, nothing to install.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

QUEUE_BASE = "https://queue.fal.run"

# Preset model endpoints on fal.ai (verified against the fal.ai docs).
MODELS = {
    "wan": "fal-ai/wan/v2.7/text-to-video",
    "wan25": "fal-ai/wan-25-preview/text-to-video",
    "veo": "fal-ai/veo3.1",
    "ltx": "fal-ai/ltx-2-19b/text-to-video",
}
VALID_ASPECTS = ("16:9", "9:16")
POLL_SECONDS = 5
TIMEOUT_SECONDS = 15 * 60

KEY_HELP = (
    "FAL_KEY is missing or invalid. Steps:\n"
    "  1. Sign up at https://fal.ai and add a small credit balance\n"
    "     (Billing page; video is billed per second of output).\n"
    "  2. Create an API key at https://fal.ai/dashboard/keys\n"
    "  3. Set it before running:\n"
    "       Windows:   set FAL_KEY=your_key\n"
    "       Mac/Linux: export FAL_KEY=your_key"
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


def api_request(method, url, api_key, payload=None):
    """One HTTP call to the fal.ai queue API. Returns (status, parsed_json)."""
    data = None
    headers = {"Authorization": f"Key {api_key}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed


def build_input(item, endpoint):
    """Build the model input payload. Field shapes differ per model family."""
    payload = {"prompt": item["prompt"], "aspect_ratio": item["aspect"]}
    if "veo" in endpoint:
        seconds = item["duration"]
        if seconds <= 4:
            payload["duration"] = "4s"
        elif seconds <= 6:
            payload["duration"] = "6s"
        else:
            payload["duration"] = "8s"
        payload["generate_audio"] = True
    elif "wan" in endpoint:
        payload["duration"] = str(item["duration"])
        payload["resolution"] = "720p"
    return payload


def generate_one(item, endpoint, api_key, out_path, index, total):
    short = (item["prompt"][:57] + "...") if len(item["prompt"]) > 60 else item["prompt"]
    print(f"[{index}/{total}] submitting to cloud ({endpoint}): {short}")

    status, body = api_request(
        "POST", f"{QUEUE_BASE}/{endpoint}", api_key, build_input(item, endpoint)
    )
    if status in (401, 403):
        print(KEY_HELP)
        sys.exit(2)
    if status == 402:
        print("  FAILED: fal.ai balance is empty. Add credit at https://fal.ai/dashboard/billing")
        return False
    if status != 200 or "status_url" not in body:
        print(f"  FAILED: submit returned status {status}: {json.dumps(body)[:300]}")
        return False

    status_url = body["status_url"]
    response_url = body["response_url"]
    waited = 0
    while waited < TIMEOUT_SECONDS:
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        status, body = api_request("GET", status_url, api_key)
        state = body.get("status", "")
        if state == "COMPLETED":
            break
        if state in ("FAILED", "ERROR"):
            print(f"  FAILED on cloud: {json.dumps(body)[:300]}")
            return False
        if waited % 30 == 0:
            print(f"  still rendering... ({waited}s)")
    else:
        print(f"  FAILED: timed out after {TIMEOUT_SECONDS // 60} minutes.")
        return False

    status, body = api_request("GET", response_url, api_key)
    video = body.get("video") or {}
    video_url = video.get("url")
    if status != 200 or not video_url:
        print(f"  FAILED: no video in result: {json.dumps(body)[:300]}")
        return False

    req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(out_path, "wb") as f:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
    print(f"  saved: {out_path}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Batch-generate AI videos from a prompt file using the fal.ai cloud API (no local GPU)."
    )
    parser.add_argument("--prompts", default="prompts.txt", help="Prompt file (.txt or .json).")
    parser.add_argument("--out", default="output-fal", help="Folder to save MP4 files in.")
    parser.add_argument("--model", default="wan",
                        help=f"Model preset ({', '.join(MODELS)}). Default: wan (cheap and fast).")
    parser.add_argument("--endpoint", default=None,
                        help="Full fal.ai endpoint id, overrides --model (example: fal-ai/veo3.1/fast).")
    parser.add_argument("--duration", type=int, default=5,
                        help="Clip length in seconds (Wan: 5/10/15, Veo: 4/6/8).")
    parser.add_argument("--aspect", default="9:16",
                        help="Aspect ratio, 16:9 or 9:16 (9:16 is for Shorts/Reels/TikTok).")
    args = parser.parse_args()

    if args.model not in MODELS:
        print(f"Unknown model '{args.model}'. Choose from: {', '.join(MODELS)}")
        sys.exit(1)
    if args.aspect not in VALID_ASPECTS:
        print(f"Unknown aspect '{args.aspect}'. Choose from: {', '.join(VALID_ASPECTS)}")
        sys.exit(1)

    api_key = os.environ.get("FAL_KEY")
    if not api_key:
        print(KEY_HELP)
        sys.exit(2)

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
        endpoint = args.endpoint or MODELS[item["model"]]
        filename = f"fal-video-{i:03d}.mp4"
        out_path = os.path.join(args.out, filename)
        if os.path.exists(out_path):
            print(f"[{i}/{total}] already exists, skipping: {out_path}")
            skipped += 1
            continue
        ok = generate_one(item, endpoint, api_key, out_path, i, total)
        if ok:
            made += 1
            manifest.append(
                {
                    "file": filename,
                    "prompt": item["prompt"],
                    "model": item["model"],
                    "endpoint": endpoint,
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
