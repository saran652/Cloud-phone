from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "app": "Cloud Phone",
        "status": "online",
        "message": "Cloud Phone server is running",
        "api_version": "1.0"
    }), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy"
    }), 200

@app.route("/connect", methods=["GET"])
def connect():
    return jsonify({
        "connected": True,
        "message": "Server connection successful",
        "cloud_android": "not_configured"
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
