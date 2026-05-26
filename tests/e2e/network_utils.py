import socket
import time


def check_port_in_use(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (ConnectionRefusedError, ConnectionResetError):
        return False


def poll_port(host, port, timeout=30):
    print(f"Polling for service on {host}:{port}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_port_in_use(host, port):
            print(f"Service on {host}:{port} is ready.")
            return True
        time.sleep(1)
    print(f"Service on {host}:{port} did not become ready within {timeout} seconds.")
    return False
