from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from werkzeug.utils import secure_filename
import os
import uuid

app = Flask(name)

STORAGE = Path(
os.environ.get("STORAGE_DIR", "/tmp/cloud_downloads")
)
STORAGE.mkdir(parents=True, exist_ok=True)

ANDROID_VERSIONS = [
{"version": "Android 11", "api_level": 30},
{"version": "Android 12", "api_level": 31},
{"version": "Android 13", "api_level": 33}
]

@app.route("/")
def home():
return jsonify({
"app": "SkyDroid Cloud Phone",
"status": "online",
"storage": "temporary",
"download_api": "/download",
"files_api": "/files",
"android_versions_api": "/api/android/versions",
"android_status_api": "/api/android/status"
})

@app.route("/health")
def health():
return jsonify({"status": "healthy"})

@app.route("/api/android/versions")
def android_versions():
return jsonify({
"app": "SkyDroid",
"status": "online",
"vm_available": False,
"versions": ANDROID_VERSIONS,
"message": "Android VM host is not configured"
})

@app.route("/api/android/status")
def android_status():
return jsonify({
"server_status": "online",
"vm_available": False,
"vm_status": "not_configured",
"message": "Flask is online, but no Android VM is running"
})

@app.route("/download", methods=["POST"])
def download_file():
data = request.get_json(silent=True) or {}
url = data.get("url", "").strip()

parsed = urlparse(url)

if parsed.scheme != "https" or not parsed.hostname:
    return jsonify({
        "error": "Valid HTTPS URL required"
    }), 400

if parsed.username or parsed.password:
    return jsonify({"error": "URL credentials not allowed"}), 400

if parsed.hostname.lower() in (
    "localhost", "127.0.0.1", "::1"
):
    return jsonify({"error": "URL not allowed"}), 400

target = None

try:
    req = Request(
        url,
        headers={"User-Agent": "SkyDroid/1.0"}
    )

    with urlopen(req, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")

        if "text/html" in content_type.lower():
            return jsonify({
                "error": "URL returns a webpage, not a direct file"
            }), 400

        filename = secure_filename(
            Path(urlparse(response.geturl()).path).name
        ) or "download.bin"

        filename = str(uuid.uuid4()) + "_" + filename
        target = STORAGE / filename

        size = 0

        with open(target, "wb") as out:
            while True:
                chunk = response.read(64 * 1024)

                if not chunk:
                    break

                size += len(chunk)

                if size > 100 * 1024 * 1024:
                    out.close()
                    target.unlink(missing_ok=True)
                    return jsonify({
                        "error": "File limit is 100 MB"
                    }), 413

                out.write(chunk)

    return jsonify({
        "status": "saved",
        "filename": filename,
        "bytes": size,
        "download_path": "/files/" + filename
    })

except Exception:
    if target is not None:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass

    return jsonify({
        "error": "Download failed. Check the direct file URL."
    }), 400

@app.route("/files")
def list_files():
return jsonify([
{
"filename": p.name,
"bytes": p.stat().st_size,
"download_path": "/files/" + p.name
}
for p in STORAGE.iterdir()
if p.is_file()
])

@app.route("/files/"path:filename" (path:filename)")
def get_file(filename):
safe_name = secure_filename(filename)

if not safe_name or safe_name != filename:
    return jsonify({"error": "Invalid filename"}), 400

return send_from_directory(
    STORAGE,
    safe_name,
    as_attachment=True
)

if name == "main":
app.run(host="0.0.0.0", port=5000)
