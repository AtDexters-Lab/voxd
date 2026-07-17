import socket

from voxd.paths import CONFIG_DIR


def _socket_path():
    return CONFIG_DIR / "voxd.sock"

def send_trigger() -> bool:
    """Connect to the running app and send 'trigger_record'."""
    path = str(_socket_path())
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(1.0)
        sock.connect(path)
        sock.sendall(b"trigger_record")
        return True
    except Exception as e:
        print(f"[IPC] Could not send trigger: {e}")
        return False
    finally:
        sock.close()
