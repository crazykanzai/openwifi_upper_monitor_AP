import subprocess
from typing import Dict, List


class IperfServerManager:
    def __init__(self, iperf_bin: str = "iperf3"):
        self.iperf_bin = iperf_bin
        self.processes: Dict[int, subprocess.Popen] = {}
        self.latest_lines: Dict[int, str] = {}

    def start_servers(self, ports: List[int]) -> Dict[int, str]:
        result = {}
        for p in ports:
            if p in self.processes and self.processes[p].poll() is None:
                result[p] = "already running"
                continue

            cmd = [self.iperf_bin, "-s", "-p", str(p), "-i", "1"]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                self.processes[p] = proc
                self.latest_lines[p] = "started"
                result[p] = "started"
            except Exception as e:
                result[p] = f"failed: {e}"
        return result

    def stop_servers(self) -> Dict[int, str]:
        result = {}
        for p, proc in list(self.processes.items()):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
                result[p] = "stopped"
            else:
                result[p] = "already exited"
            self.processes.pop(p, None)
        return result

    def status(self, ports: List[int]) -> Dict[int, bool]:
        s = {}
        for p in ports:
            proc = self.processes.get(p)
            s[p] = bool(proc and proc.poll() is None)
        return s

    def read_latest_output(self) -> Dict[int, str]:
        for p, proc in self.processes.items():
            if not proc or not proc.stdout or proc.poll() is not None:
                continue
            try:
                line = proc.stdout.readline()
                if line:
                    self.latest_lines[p] = line.strip()
            except Exception:
                pass
        return dict(self.latest_lines)
