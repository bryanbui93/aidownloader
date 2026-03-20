# 🎬 AI Video Downloader (`aidownloader`)

A terminal tool to batch-download public videos from **TikTok**, **Douyin**, **Facebook Reels**, and **YouTube Shorts** using an Excel file as input.

---

## ✨ Features

- 📊 **Smart Excel parsing** — auto-detects the URL column, no config needed
- 📁 **Date-organized output** — videos saved to `downloads/YYYY-MM-DD/`
- 🔁 **Retry logic** — retries failed URLs up to 3× with exponential back-off
- ⚡ **Parallel mode** — configurable worker count for faster batch downloads
- 🎨 **Rich terminal UI** — live progress bar + per-URL status table
- 📋 **Failure report** — failed URLs saved to `failed_links.xlsx` automatically

---

## 📦 Installation

```bash
# Clone and install (creates the `aidownloader` command)
cd aidownloader
pip install -e .
```

**Requirements:** Python 3.9+

---

## 🚀 Usage

### Basic (sequential)
```bash
aidownloader --input links.xlsx
```

### Custom output folder
```bash
aidownloader --input links.xlsx --output ./my-videos
```

### Parallel downloads (4 workers)
```bash
aidownloader --input links.xlsx --workers 4
```

### Custom retry count
```bash
aidownloader --input links.xlsx --retries 5
```

### Dry run (parse only, no downloads)
```bash
aidownloader --input links.xlsx --dry-run
```

### Full options
```
usage: aidownloader [-h] --input INPUT [--output OUTPUT] [--workers WORKERS]
                    [--retries RETRIES] [--dry-run]

Options:
  --input,   -i   Path to Excel file (.xlsx or .xls)          [required]
  --output,  -o   Output folder                               [default: ./downloads]
  --workers, -w   Number of parallel workers                  [default: 1 = sequential]
  --retries, -r   Max retries per URL on failure              [default: 3]
  --dry-run        List URLs without downloading
```

---

## 📋 Excel File Format

The tool **automatically detects** which column contains video URLs — no special formatting required.

| Any header you like | Notes column | **URL column** |
|---------------------|--------------|----------------|
| Row 1 data          | Some note    | https://www.tiktok.com/@user/video/123 |
| Row 2 data          | Some note    | https://www.facebook.com/reel/456 |

**Supported URL formats:**

| Platform | Example URL |
|----------|-------------|
| TikTok | `https://www.tiktok.com/@user/video/...` |
| Douyin | `https://www.douyin.com/video/...` |
| Facebook Reels | `https://www.facebook.com/reel/...` or `https://fb.watch/...` |
| YouTube Shorts | `https://www.youtube.com/shorts/...` |

---

## 📂 Output Structure

```
downloads/
└── 2026-03-18/
    ├── username_videoId.mp4
    ├── anotherUser_videoId.mp4
    └── ...
failed_links.xlsx     ← auto-generated if any downloads fail
```

---

## ⚠️ Known Limitations

| Platform | Notes |
|----------|-------|
| **Douyin** | Some videos may require region access or cookies. Download may fail outside of China. |
| **Facebook** | Works for **public** reels only. Private/login-gated content will fail. |
| **TikTok** | Works for public videos. |
| **YouTube Shorts** | Works reliably for all public Shorts. |
| **Parallel mode** | Using many workers (`--workers 10+`) may trigger rate limiting on some platforms. |

---

## 🛠️ Development

```bash
# Install dev dependencies
pip install -e .

# Test with a dry run
aidownloader --input sample_links.xlsx --dry-run
```

---

## 📄 License

MIT
