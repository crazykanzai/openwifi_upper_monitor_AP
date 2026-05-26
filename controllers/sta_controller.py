import paramiko
from typing import Dict, List, Tuple


class STAController:
    def __init__(self, sta_list: List[Dict], ubuntu_cfg: Dict, experiment_cfg: Dict, timeout: int = 8):
        self.sta_list = sta_list
        self.ubuntu_cfg = ubuntu_cfg
        self.experiment_cfg = experiment_cfg
        self.timeout = timeout

    def _connect(self, sta: Dict) -> paramiko.SSHClient:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": sta["host"],
            "port": sta.get("port", 22),
            "username": sta["username"],
            "timeout": self.timeout,
        }
        if sta.get("key_path"):
            connect_kwargs["key_filename"] = sta["key_path"]
        else:
            connect_kwargs["password"] = sta.get("password", "")

        c.connect(**connect_kwargs)
        return c

    def _run_sta_cmd(self, sta: Dict, cmd: str, timeout: int = 8) -> Tuple[bool, str, str]:
        try:
            client = self._connect(sta)
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode(errors="ignore")
            err = stderr.read().decode(errors="ignore")
            rc = stdout.channel.recv_exit_status()
            client.close()
            return rc == 0, out, err
        except Exception as e:
            return False, "", str(e)

    def test_all_connections(self) -> Dict[str, Tuple[bool, str]]:
        result = {}
        for sta in self.sta_list:
            try:
                c = self._connect(sta)
                c.close()
                result[sta["name"]] = (True, "OK")
            except Exception as e:
                result[sta["name"]] = (False, str(e))
        return result

    def start_iperf_client(self, sta: Dict, bandwidth: str = None, duration: int = None) -> Tuple[bool, str]:
        bw = bandwidth or self.experiment_cfg.get("default_bandwidth", "20M")
        t = duration or self.experiment_cfg.get("default_duration", 3600)
        pkt_len = self.experiment_cfg.get("default_packet_len", 1470)
        para = self.experiment_cfg.get("default_parallel", 4)

        server_ip = self.ubuntu_cfg["server_ip"]
        port = sta["iperf_port"]

        cmd = (
            f"nohup iperf3 -c {server_ip} -p {port} -u -b {bw} -t {t} -l {pkt_len} -P {para} "
            f">/tmp/iperf3_{sta['name']}.log 2>&1 &"
        )
        ok, out, err = self._run_sta_cmd(sta, cmd, timeout=8)
        return ok, out + err

    def stop_iperf_client(self, sta: Dict) -> Tuple[bool, str]:
        cmd = "pkill -f 'iperf3 -c' || true"
        ok, out, err = self._run_sta_cmd(sta, cmd, timeout=8)
        return ok, out + err

    def start_all(self, bandwidth: str = None, duration: int = None) -> Dict[str, Tuple[bool, str]]:
        result = {}
        for sta in self.sta_list:
            result[sta["name"]] = self.start_iperf_client(sta, bandwidth, duration)
        return result

    def stop_all(self) -> Dict[str, Tuple[bool, str]]:
        result = {}
        for sta in self.sta_list:
            result[sta["name"]] = self.stop_iperf_client(sta)
        return result
