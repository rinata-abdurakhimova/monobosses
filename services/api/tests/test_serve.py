"""Regression checks for Railway's IPv4 health check / IPv6 private networking."""
import http.client
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

_spec = importlib.util.spec_from_file_location(
    "deployment_serve", Path(__file__).resolve().parents[1] / "scripts" / "serve.py")
assert _spec is not None and _spec.loader is not None
_serve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_serve)
create_listener = _serve.create_listener


@unittest.skipUnless(socket.has_dualstack_ipv6(), "Dual-stack networking unavailable")
class DeploymentListenerTests(unittest.TestCase):
    def test_listener_accepts_ipv4_and_ipv6(self):
        with create_listener(0) as listener:
            port = listener.getsockname()[1]
            listener.settimeout(2)
            for host in ("127.0.0.1", "::1"):
                with socket.create_connection((host, port), timeout=2) as client:
                    accepted, _ = listener.accept()
                    with accepted:
                        accepted.sendall(b"connected")
                        self.assertEqual(client.recv(32), b"connected")

    @unittest.skipUnless(importlib.util.find_spec("uvicorn"), "API dependencies unavailable")
    def test_api_health_is_reachable_on_both_address_families(self):
        with create_listener(0) as probe:
            port = probe.getsockname()[1]
        api_root = Path(__file__).resolve().parents[1]
        environment = {**os.environ, "PORT": str(port), "PYTHONDONTWRITEBYTECODE": "1"}
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(api_root / "src"), environment.get("PYTHONPATH", "")])
        process = subprocess.Popen(
            [sys.executable, str(api_root / "scripts" / "serve.py")],
            env=environment, cwd=api_root, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        try:
            for host in ("127.0.0.1", "::1"):
                deadline = time.monotonic() + 15
                while True:
                    connection = http.client.HTTPConnection(host, port, timeout=1)
                    try:
                        connection.request("GET", "/health")
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), b'{"status":"ok"}')
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail(f"API failed to serve /health over {host}")
                        time.sleep(0.05)
                    finally:
                        connection.close()
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
