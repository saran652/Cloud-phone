
from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from werkzeug.utils import secure_filename
import os
import uuid
import ipaddress
import socket
import hmac

app = Flask(__name__)

STORAGE = Path(os.environ.get("STORAGE_DIR", "/tmp/cloud_downloads"))
STORAGE.mkdir(parents=True, exist_ok=True)

MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_UPLOAD = 10 * 1024 * 1024

# Limit incoming upload requests
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD + 1024 * 1024

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
        "health_api": "/health",
        "android_versions_api": "/api/android/versions",
        "android_status_api": "/api/android/status",
        "download_api": "/download",
        "upload_api": "/upload",
        "files_api": "/files"
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
        "message": "Flask server is running; an Android VM host is still needed"
    })


def is_public_host(hostname):
    try:
        addresses = socket.getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM
        )
        if not addresses:
            return False

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                return False

        return True
    except (ValueError, OSError):
        return False


def get_upload_token():
    return os.environ.get("UPLOAD_TOKEN", "")


@app.route("/upload", methods=["POST"])
def upload_file():
    expected_token = get_upload_token()
    supplied_token = request.headers.get("X-Upload-Token", "")

    if not expected_token:
        return jsonify({
            "error": "Upload is not configured on the server"
        }), 503

    if not hmac.compare_digest(supplied_token, expected_token):
        return jsonify({"error": "Unauthorized"}), 401

    uploaded = request.files.get("file")

    if uploaded is None or not uploaded.filename:
        return jsonify({
            "error": "Missing file field"
        }), 400

    filename = secure_filename(uploaded.filename)

    if not filename:
        return jsonify({"error": "Invalid filename"}), 400

    filename = str(uuid.uuid4()) + "_" + filename
    target = STORAGE / filename

    try:
        uploaded.save(target)

        return jsonify({
            "status": "saved",
            "filename": filename,
            "bytes": target.stat().st_size,
            "download_path": "/files/" + filename
        }), 201

    except OSError:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass

        return jsonify({"error": "Could not save file"}), 500


@app.route("/download", methods=["POST"])
def download_file():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")

    if not isinstance(url, str):
        return jsonify({"error": "URL must be text"}), 400

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme != "https" or not parsed.hostname:
        return jsonify({
            "error": "A valid HTTPS direct-file URL is required"
        }), 400

    if parsed.username or parsed.password:
        return jsonify({"error": "URL credentials are not allowed"}), 400

    if not is_public_host(parsed.hostname):
        return jsonify({"error": "Host is not allowed"}), 400

    target = None

    try:
        req = Request(
            url,
            headers={"User-Agent": "SkyDroid/1.0"}
        )

        with urlopen(req, timeout=30) as response:
            final_url = urlparse(response.geturl())

            if (
                final_url.scheme != "https"
                or not final_url.hostname
                or not is_public_host(final_url.hostname)
            ):
                return jsonify({
                    "error": "Redirect destination is not allowed"
                }), 400

            content_type = response.headers.get("Content-Type", "")

            if "text/html" in content_type.lower():
                return jsonify({
                    "error": "This URL opens a webpage, not a direct file"
                }), 400

            filename = secure_filename(
                Path(final_url.path).name
            ) or "download.bin"

            filename = str(uuid.uuid4()) + "_" + filename
            target = STORAGE / filename
            size = 0

            with open(target, "wb") as out:
                while True:
                    chunk = response.read(65536)

                    if not chunk:
                        break

                    size += len(chunk)

                    if size > MAX_DOWNLOAD:
                        out.close()
                        target.unlink(missing_ok=True)
                        return jsonify({
                            "error": "Maximum download size is 100 MB"
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
            "error": "Download failed. Check the direct HTTPS file URL."
        }), 400


@app.route("/files", methods=["GET"])
def list_files():
    files = []

    for item in STORAGE.iterdir():
        if item.is_file():
            files.append({
                "filename": item.name,
                "bytes": item.stat().st_size,
                "download_path": "/files/" + item.name
            })

    return jsonify(files)


@app.route("/files/<path:filename>", methods=["GET"])
def get_file(filename):
    safe_name = secure_filename(filename)

    if not safe_name or safe_name != filename:
        return jsonify({"error": "Invalid filename"}), 400

    return send_from_directory(
        str(STORAGE),
        safe_name,
        as_attachment=True
    )


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Not Found",
        "message": "Check the URL path or server routes"
    }), 404


@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "Request too large",
        "message": "Upload limit is 10 MB"
    }), 413


@app.errorhandler(500)
def server_error(error):
    return jsonify({
        "error": "Internal server error"
    }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
