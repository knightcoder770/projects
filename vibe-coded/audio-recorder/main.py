import webview
import threading
import server

def start_server():
    server.app.run(port=5000, debug=False)

if __name__ == "__main__":
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    webview.create_window("🎙️ Audio Recorder", "http://localhost:5000", width=480, height=620, resizable=False)
    webview.start()
