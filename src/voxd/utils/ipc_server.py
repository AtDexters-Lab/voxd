import socket
import threading
import time
from pathlib import Path

def _socket_path():
    return Path.home() / ".config" / "voxd" / "voxd.sock"

# Minimum interval between accepted trigger_record messages (seconds).
# Prevents keyboard auto-repeat on the hotkey from spawning duplicate
# recording/transcription threads.
_DEBOUNCE_SEC = 0.5

def start_ipc_server(trigger_callback):
    """Starts a background thread that listens for 'trigger_record' and calls trigger_callback()."""
    sock_path = _socket_path()
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen()

    last_trigger = 0.0
    lock = threading.Lock()

    def _serve_loop():
        nonlocal last_trigger
        while True:
            conn, _ = server.accept()
            try:
                data = conn.recv(1024).strip()
                if data == b"trigger_record":
                    fire = False
                    with lock:
                        now = time.monotonic()
                        if now - last_trigger >= _DEBOUNCE_SEC:
                            last_trigger = now
                            fire = True
                    if fire:
                        trigger_callback()
            finally:
                conn.close()

    t = threading.Thread(target=_serve_loop, daemon=True)
    t.start()
