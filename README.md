# AI Video Batch Maker

Give this tool a file of prompts. It makes one AI video (MP4) for every prompt,
automatically. It runs on the **free** pollinations.ai video API.

## How it works

1. You write your video prompts in `prompts.txt` (one prompt per line).
2. You run `python generate.py`.
3. It creates `output/video-001.mp4`, `output/video-002.mp4`, and so on.
4. A file `output/manifest.json` records which prompt made which video.

## Step 1: get a free API key

Sign up at **https://enter.pollinations.ai**. It is free and no credit card is
needed. Copy your API key.

## Step 2: download this repo

Either click the green **Code** button on GitHub and choose **Download ZIP**,
or clone it:

```
git clone https://github.com/JahanzaibShahzad/ai-video-batch-maker
cd ai-video-batch-maker
```

## Step 3: install Python and the requirements

Install **Python 3.9 or newer** from https://www.python.org/downloads/
(tick "Add python to PATH" on Windows). Then install the one dependency:

```
pip install -r requirements.txt
```

## Step 4: set your API key

On Windows (Command Prompt):

```
set POLLINATIONS_API_KEY=your_key_here
```

On Mac or Linux (Terminal):

```
export POLLINATIONS_API_KEY=your_key_here
```

Replace `your_key_here` with the key from Step 1.

## Step 5: write your prompts

Open `prompts.txt` and write one prompt per line. Example:

```
A cute cat astronaut floating in space, cartoon style
Ocean waves crashing on rocks at sunrise, cinematic drone shot
```

Lines starting with `#` are ignored.

**Advanced option:** create a file named `prompts.json` to set per-video
options (model, duration, aspect ratio). If `prompts.json` exists, it is used
instead of `prompts.txt`:

```json
[
  { "prompt": "A cute cat astronaut floating in space, cartoon style", "duration": 8, "model": "wan-fast", "aspect": "9:16" },
  { "prompt": "Ocean waves crashing on rocks at sunrise, cinematic drone shot", "duration": 12, "model": "veo", "aspect": "16:9" }
]
```

## Step 6: run it

```
python generate.py
```

Videos appear in the `output/` folder.

## Options

| Flag | Default | What it does |
| ---- | ------- | ------------ |
| `--prompts` | `prompts.txt` | Which prompt file to read |
| `--out` | `output` | Folder to save videos in |
| `--model` | `wan-fast` | Video model: `wan-fast` (fastest), `wan`, `veo` (best quality), `seedance-2.0` |
| `--duration` | `8` | Clip length in seconds |
| `--aspect` | `16:9` | `16:9` for YouTube, `9:16` for Shorts, Reels and TikTok |

Example: make vertical Shorts with the best model:

```
python generate.py --model veo --aspect 9:16 --duration 10
```

## Honest notes

- The free tier gives you hourly compute credits. Very large batches may need
  to run in chunks. The script **resumes where it stopped**: videos that
  already exist in `output/` are skipped, so you can just run it again.
- Each clip takes a few minutes to generate. 10 prompts can take 30 to 60
  minutes in total.
- If you get a 401 error, your API key is missing or wrong. Repeat Step 4.
- If you get a 402 error, it means "insufficient pollen balance". Pollen is
  pollinations.ai's free credit currency. New accounts can show 0 pollen.
  Fix: open https://enter.pollinations.ai, check your balance, and complete
  the free Quests (for example starring their GitHub repo) to earn free
  pollen. Free pollen grants also renew daily. No credit card is needed.
  The default model `ltx-2` is the free-tier video model; paid models like
  `veo` need more pollen.
- If you get rate limited (429), the script waits 60 seconds and retries
  automatically.

## License

MIT. See the `LICENSE` file.
