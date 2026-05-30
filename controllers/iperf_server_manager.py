import os
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


class IperfServerManager:
    def __init__(self, iperf_bin: str = "iperf3"):
        self.iperf_bin = iperf_bin
        self.processes: Dict[int, subprocess.Popen] = {}
        self.log_files: Dict[int, object] = {}

    def start_server(self, port: int, log_path: str) -> Tuple[bool, str]:
        proc = self.processes.get(port)
        if proc and proc.poll() is None:
            return True, f"port {port} already running"
        if proc:
            self.processes.pop(port, None)
            log_file = self.log_files.pop(port, None)
            if log_file:
                log_file.close()

        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        f = open(path, "a", encoding="utf-8")

        cmd = [self.iperf_bin, "-s", "-p", str(port), "-i", "1", "--forceflush"]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
                text=True,
            )
            self.processes[port] = proc
            self.log_files[port] = f
            return True, f"port {port} started"
        except Exception as e:
            f.close()
            return False, f"port {port} start failed: {e}"

    def stop_server(self, port: int) -> Tuple[bool, str]:
        proc = self.processes.get(port)
        if not proc:
            return True, f"port {port} not running"

        if proc.poll() is not None:
            self.processes.pop(port, None)
            log_file = self.log_files.pop(port, None)
            if log_file:
                log_file.close()
            return True, f"port {port} already exited"

        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=3)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        self.processes.pop(port, None)
        log_file = self.log_files.pop(port, None)
        if log_file:
            log_file.close()
        return True, f"port {port} stopped"

    def start_all_servers(self, ports: List[int], log_dir: str) -> Dict[int, str]:
        result = {}
        for p in ports:
            ok, msg = self.start_server(p, str(Path(log_dir) / f"iperf_server_{p}.log"))
            result[p] = msg if ok else f"ERROR: {msg}"
        return result

    def stop_all_servers(self) -> Dict[int, str]:
        result = {}
        for p in list(self.processes.keys()):
            ok, msg = self.stop_server(p)
            result[p] = msg if ok else f"ERROR: {msg}"
        return result

    def get_server_status(self, port: int) -> bool:
        proc = self.processes.get(port)
        return bool(proc and proc.poll() is None)
