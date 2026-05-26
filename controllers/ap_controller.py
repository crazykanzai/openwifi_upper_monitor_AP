import paramiko
from typing import Dict, List, Tuple

from utils.parsers import parse_station_dump


class APController:
    def __init__(self, cfg: Dict, timeout: int = 8):
        self.cfg = cfg
        self.timeout = timeout

    def _connect(self) -> paramiko.SSHClient:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.cfg["host"],
            "port": self.cfg.get("port", 22),
            "username": self.cfg["username"],
            "timeout": self.timeout,
        }
        if self.cfg.get("key_path"):
            connect_kwargs["key_filename"] = self.cfg["key_path"]
        else:
            connect_kwargs["password"] = self.cfg.get("password", "")

        c.connect(**connect_kwargs)
        return c

    def test_connection(self) -> Tuple[bool, str]:
        try:
            client = self._connect()
            client.close()
            return True, "AP SSH 连接成功"
        except Exception as e:
            return False, f"AP SSH 连接失败: {e}"

    def run_command(self, cmd: str, timeout: int = 8) -> Tuple[bool, str, str]:
        try:
            client = self._connect()
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")
            rc = stdout.channel.recv_exit_status()
            client.close()
            return rc == 0, out, err
        except Exception as e:
            return False, "", str(e)

    def get_station_dump_raw(self) -> Tuple[bool, str, str]:
        iface = self.cfg.get("interface", "sdr0")
        return self.run_command(f"iw dev {iface} station dump", timeout=10)

    def get_station_metrics(self) -> Tuple[bool, List[Dict], str]:
        ok, out, err = self.get_station_dump_raw()
        if not ok:
            return False, [], err
        try:
            parsed = parse_station_dump(out)
            return True, parsed, ""
        except Exception as e:
            return False, [], f"解析 station dump 失败: {e}"

    def set_cw(self, cwmin_exp: int, cwmax_exp: int) -> Tuple[bool, str]:
        cmds = [
            f"hostapd_cli set wmm_ac_be_cwmin {cwmin_exp}",
            f"hostapd_cli set wmm_ac_be_cwmax {cwmax_exp}",
            "hostapd_cli update_beacon",
        ]

        outputs = []
        for cmd in cmds:
            ok, out, err = self.run_command(cmd, timeout=8)
            outputs.append(f"$ {cmd}\n{out}{err}")
            if not ok:
                return False, "\n".join(outputs)

        return True, "\n".join(outputs)
