import json
import os
import queue
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, Response, jsonify, render_template_string, request, stream_with_context

from downloader.downloader import download_video
from downloader.excel_parser import parse_excel
from downloader.models import DownloadJob, DownloadStatus

app = Flask(__name__, static_folder="static", template_folder="static")

# ── Cross-platform Downloads folder ──────────────────────────────────────────

def get_downloads_dir() -> Path:
    d = Path.home() / "Downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── In-memory session store ───────────────────────────────────────────────────
# session_id -> Queue of SSE event dicts
_sessions: Dict[str, queue.Queue] = {}
_sessions_lock = threading.Lock()


def _new_session() -> tuple[str, queue.Queue]:
    sid = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    with _sessions_lock:
        _sessions[sid] = q
    return sid, q


def _push(q: queue.Queue, event_type: str, data: dict):
    q.put({"type": event_type, "data": data})


# ── Background download workers ───────────────────────────────────────────────

def _run_downloads(jobs: List[DownloadJob], output_dir: Path, q: queue.Queue,
                   cookies_browser: Optional[str], use_cwd: bool):
    total = len(jobs)
    succeeded = 0
    failed = 0

    for idx, job in enumerate(jobs):
        _push(q, "progress", {
            "index": idx, "total": total,
            "url": job.url, "platform": job.platform.value,
            "status": "downloading", "attempt": 1,
        })

        def on_attempt(attempt, i=idx):
            _push(q, "progress", {
                "index": i, "total": total,
                "url": job.url, "platform": job.platform.value,
                "status": "downloading", "attempt": attempt,
            })

        result = download_video(
            job, str(output_dir),
            max_retries=3,
            on_attempt=on_attempt,
            cookies_browser=cookies_browser,
            use_cwd=use_cwd,
        )

        if result.status == DownloadStatus.SUCCESS:
            succeeded += 1
            _push(q, "result", {
                "index": idx, "total": total,
                "url": job.url, "platform": job.platform.value,
                "status": "success",
                "filename": os.path.basename(result.output_path or ""),
                "output_dir": str(output_dir),
            })
        else:
            failed += 1
            _push(q, "result", {
                "index": idx, "total": total,
                "url": job.url, "platform": job.platform.value,
                "status": "failed",
                "error": result.error or "Unknown error",
            })

    _push(q, "done", {
        "succeeded": succeeded, "failed": failed, "total": total,
        "output_dir": str(output_dir),
    })


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/download/url", methods=["POST"])
def download_url():
    body = request.get_json(force=True)
    url = (body.get("url") or "").strip()
    cookies_browser = body.get("cookies_browser") or None

    if not url:
        return jsonify({"error": "URL is required"}), 400

    job = DownloadJob(url=url, row_number=1)
    output_dir = get_downloads_dir()

    sid, q = _new_session()
    _push(q, "start", {"total": 1, "mode": "url", "output_dir": str(output_dir)})

    thread = threading.Thread(
        target=_run_downloads,
        args=([job], output_dir, q, cookies_browser, True),
        daemon=True,
    )
    thread.start()
    return jsonify({"session_id": sid, "output_dir": str(output_dir)})


@app.route("/api/download/excel", methods=["POST"])
def download_excel():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    cookies_browser = request.form.get("cookies_browser") or None

    # Save to temp file
    suffix = Path(f.filename).suffix if f.filename else ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        jobs = parse_excel(tmp_path)
    except Exception as exc:
        os.unlink(tmp_path)
        return jsonify({"error": str(exc)}), 400
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not jobs:
        return jsonify({"error": "No supported video URLs found in file"}), 400

    # Create dated subfolder inside Downloads
    from datetime import date
    folder_name = f"aidownloader-{date.today().strftime('%Y-%m-%d')}"
    output_dir = get_downloads_dir() / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    sid, q = _new_session()
    _push(q, "start", {
        "total": len(jobs), "mode": "excel", "output_dir": str(output_dir)
    })

    thread = threading.Thread(
        target=_run_downloads,
        args=(jobs, output_dir, q, cookies_browser, True),
        daemon=True,
    )
    thread.start()
    return jsonify({
        "session_id": sid,
        "total": len(jobs),
        "output_dir": str(output_dir),
    })


@app.route("/api/stream/<session_id>")
def stream(session_id: str):
    with _sessions_lock:
        q = _sessions.get(session_id)
    if q is None:
        return Response("Session not found", status=404)

    def generate():
        while True:
            try:
                event = q.get(timeout=60)
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"
                continue
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
            if event["type"] == "done":
                with _sessions_lock:
                    _sessions.pop(session_id, None)
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def run_web(host="127.0.0.1", port=5500, debug=False):
    import webbrowser
    print(f"\n  🎬 AI Downloader UI → http://{host}:{port}\n")
    if not debug:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_web(debug=True)
