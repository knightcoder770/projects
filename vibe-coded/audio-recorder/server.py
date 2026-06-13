from flask import Flask, request, jsonify, send_from_directory
import os, uuid, subprocess, json

app = Flask(__name__, static_folder="static", template_folder="static")
SAVE_DIR = os.path.join(os.path.expanduser("~"), "AudioRecordings")
os.makedirs(SAVE_DIR, exist_ok=True)

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/save-audio", methods=["POST"])
def save_audio():
    try:
        audio_file = request.files["audio"]
        device_name = request.form.get("device", "unknown").replace(" ", "_")[:30]
        raw_path = os.path.join(SAVE_DIR, f"_tmp_{uuid.uuid4().hex}.webm")
        mp3_path = os.path.join(SAVE_DIR, f"rec_{device_name}_{uuid.uuid4().hex[:6]}.mp3")
        audio_file.save(raw_path)

        # Convert to mp3 using ffmpeg
        result = subprocess.run([
            "ffmpeg", "-y", "-i", raw_path,
            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            mp3_path
        ], capture_output=True)
        
        os.remove(raw_path)

        if result.returncode == 0:
            return jsonify({"success": True, "path": mp3_path})
        else:
            return jsonify({"success": False, "error": result.stderr.decode()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/recordings")
def list_recordings():
    files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".mp3")]
    files.sort(reverse=True)
    return jsonify(files)

@app.route("/play/<filename>")
def play_file(filename):
    return send_from_directory(SAVE_DIR, filename)

@app.route("/delete/<filename>", methods=["DELETE"])
def delete_file(filename):
    try:
        os.remove(os.path.join(SAVE_DIR, filename))
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})