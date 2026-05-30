from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import time

import paramiko

from utils.parsers import parse_station_dump


class APController:
    def __init__(self, cfg: Dict, timeout: int = 8):
        self.cfg = cfg
        self.timeout = timeout

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = {
            "hostname": self.cfg["host"],
            "port": self.cfg.get("port", 22),
            "username": self.cfg["username"],
            "timeout": self.timeout,
        }
        if self.cfg.get("key_path"):
            kwargs["key_filename"] = self.cfg["key_path"]
        else:
            kwargs["password"] = self.cfg.get("password", "")

        client.connect(**kwargs)
        return client

    def _run_command(self, cmd: str, timeout: int = 10) -> Tuple[bool, str, str]:
        client = None
        try:
            client = self._connect()
            _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")
            rc = stdout.channel.recv_exit_status()
            return rc == 0, out.strip(), err.strip()
        except Exception as e:
            return False, "", str(e)
        finally:
            if client:
                client.close()

    def run_ssh_binary_command(self, command: str, local_output_path: str, timeout_sec: int = 60) -> Dict:
        log_lines = [f"$ {command}"]
        client = None
        channel = None
        tmp_path = None
        try:
            client = self._connect()
            transport = client.get_transport()
            if transport is None:
                return {"ok": False, "log": "SSH transport 不可用"}

            channel = transport.open_session(timeout=timeout_sec)
            channel.settimeout(2.0)
            channel.exec_command(command)

            local_path = Path(local_output_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = local_path.with_name(f"{local_path.name}.tmp")

            total = 0
            start = time.monotonic()
            timed_out = False
            with tmp_path.open("wb") as f:
                while True:
                    if time.monotonic() - start > timeout_sec:
                        timed_out = True
                        log_lines.append(f"命令超过 {timeout_sec}s，已中止。")
                        channel.close()
                        break

                    if channel.recv_ready():
                        data = channel.recv(65535)
                        if data:
                            f.write(data)
                            total += len(data)

                    if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                        break

                    if channel.recv_stderr_ready():
                        err_chunk = channel.recv_stderr(4096)
                        if err_chunk:
                            log_lines.append(err_chunk.decode(errors="ignore").strip())

                    time.sleep(0.05)

                rc = -1 if timed_out else channel.recv_exit_status()

            if rc == 0:
                tmp_path.replace(local_path)
            elif tmp_path.exists():
                tmp_path.unlink()

            return {"ok": rc == 0, "bytes": total, "rc": rc, "log": "\n".join([x for x in log_lines if x])}
        except Exception as e:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
            return {"ok": False, "log": f"binary command 执行异常: {e}"}
        finally:
            if channel and not channel.closed:
                channel.close()
            if client:
                client.close()

    def test_ap_connection(self) -> Tuple[bool, str]:
        ok, out, err = self._run_command("echo AP_OK", timeout=6)
        if ok:
            return True, out or "AP SSH 连接成功"
        return False, f"AP SSH 连接失败: {err}"

    def update_beacon(self) -> Tuple[bool, str]:
        ok, out, err = self._run_command("hostapd_cli update_beacon", timeout=8)
        return ok, out if ok else err

    def set_cw(self, cwmin_exp: int, cwmax_exp: int) -> Tuple[bool, str]:
        cmds = [
            f"hostapd_cli set wmm_ac_be_cwmin {cwmin_exp}",
            f"hostapd_cli set wmm_ac_be_cwmax {cwmax_exp}",
            "hostapd_cli update_beacon",
        ]
        logs = []
        for cmd in cmds:
            ok, out, err = self._run_command(cmd, timeout=8)
            logs.append(f"$ {cmd}\n{out or err}")
            if not ok:
                return False, "\n".join(logs)
        return True, "\n".join(logs)

    def ensure_monitor_interface(self, monitor_iface: str = "mon0", phy: str = "phy0") -> Dict:
        logs = []

        ok, out, _ = self._run_command(f"ip link show {monitor_iface}", timeout=6)
        exists = ok and monitor_iface in out
        logs.append(f"检查网卡 {monitor_iface}: {'已存在' if exists else '不存在'}")

        if not exists:
            cmd = f"iw phy {phy} interface add {monitor_iface} type monitor"
            ok, out, err = self._run_command(cmd, timeout=8)
            logs.append(f"$ {cmd}\n{out or err}")
            if not ok:
                return {"ok": False, "log": "\n".join(logs)}

        cmd_ifconfig = f"ifconfig {monitor_iface} up"
        ok_if, out_if, err_if = self._run_command(cmd_ifconfig, timeout=8)
        logs.append(f"$ {cmd_ifconfig}\n{out_if or err_if}")
        if not ok_if:
            cmd_ip = f"ip link set {monitor_iface} up"
            ok_ip, out_ip, err_ip = self._run_command(cmd_ip, timeout=8)
            logs.append(f"$ {cmd_ip}\n{out_ip or err_ip}")
            if not ok_ip:
                return {"ok": False, "log": "\n".join(logs)}

        ok, out, err = self._run_command(f"ip link show {monitor_iface}", timeout=6)
        logs.append(f"最终检查 {monitor_iface}: {out or err}")
        if not ok:
            return {"ok": False, "log": "\n".join(logs)}

        return {"ok": True, "log": "\n".join(logs)}

    def capture_monitor_pcap(self, local_path: str, monitor_iface: str = "mon0", packet_count: int = 1000, timeout_sec: int = 60) -> Dict:
        cmd = f"tcpdump -U -s 0 -i {monitor_iface} -c {int(packet_count)} -w -"
        result = self.run_ssh_binary_command(cmd, local_path, timeout_sec=timeout_sec)

        if not result.get("ok"):
            return {"ok": False, "log": result.get("log", "tcpdump 执行失败")}

        fpath = Path(local_path)
        size = fpath.stat().st_size if fpath.exists() else 0
        if size < 24:
            return {"ok": False, "log": f"抓包文件过小或为空: {local_path} (size={size})"}

        return {"ok": True, "path": str(fpath), "size": size, "log": result.get("log", "")}

    def capture_cw_check_pcap(self, experiment_name: str, cwmin_exp: int, cwmax_exp: int, local_base_dir: str = "data/pcaps", monitor_iface: str = "mon0", phy: str = "phy0", packet_count: int = 1000, timeout_sec: int = 60) -> Dict:
        exp_dir = Path(local_base_dir) / experiment_name
        exp_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cw_check_{ts}_ecw_{cwmin_exp}_{cwmax_exp}.pcap"
        local_path = exp_dir / filename

        logs = []
        ensure_res = self.ensure_monitor_interface(monitor_iface=monitor_iface, phy=phy)
        logs.append(ensure_res.get("log", ""))
        if not ensure_res.get("ok"):
            return {"ok": False, "path": str(local_path), "log": "\n".join(logs)}

        cap_res = self.capture_monitor_pcap(
            local_path=str(local_path),
            monitor_iface=monitor_iface,
            packet_count=packet_count,
            timeout_sec=timeout_sec,
        )
        logs.append(cap_res.get("log", ""))
        if not cap_res.get("ok"):
            return {"ok": False, "path": str(local_path), "log": "\n".join(logs)}

        return {"ok": True, "path": str(local_path), "size": cap_res.get("size", 0), "log": "\n".join(logs)}

    def get_station_dump(self) -> Tuple[bool, str, str]:
        iface = self.cfg.get("interface", "sdr0")
        return self._run_command(f"iw dev {iface} station dump", timeout=12)

    def parse_station_dump(self, dump_text: str) -> List[Dict]:
        return parse_station_dump(dump_text)
