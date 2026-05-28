from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from streamlit_autorefresh import st_autorefresh

from controllers.ap_controller import APController
from controllers.iperf_server_manager import IperfServerManager
from utils.experiment import append_station_rows, default_experiment_name, ensure_experiment_dir
from utils.logger import setup_logger
from utils.parsers import compute_station_deltas


st.set_page_config(page_title="OpenWiFi / AntSDR AP Upper Monitor", layout="wide")
logger = setup_logger()
BASE_LOG_DIR = Path("data/logs")


def load_config(path: str = "config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cw_real(exp: int) -> int:
    return (2 ** int(exp)) - 1


def add_log(message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{ts}] {message}")
    st.session_state.logs = st.session_state.logs[-300:]
    logger.info(message)


def init_state() -> None:
    if "cfg" not in st.session_state:
        st.session_state.cfg = load_config()
    if "ap_ctrl" not in st.session_state:
        st.session_state.ap_ctrl = APController(st.session_state.cfg["ap"])
    if "iperf_mgr" not in st.session_state:
        st.session_state.iperf_mgr = IperfServerManager()
    if "logs" not in st.session_state:
        st.session_state.logs = []
    if "ap_online" not in st.session_state:
        st.session_state.ap_online = False
    if "sampling_active" not in st.session_state:
        st.session_state.sampling_active = False
    if "prev_station_map" not in st.session_state:
        st.session_state.prev_station_map = {}
    if "latest_rows" not in st.session_state:
        st.session_state.latest_rows = []
    if "history_rows" not in st.session_state:
        st.session_state.history_rows = []
    if "last_pcap_path" not in st.session_state:
        st.session_state.last_pcap_path = ""
    if "last_csv_path" not in st.session_state:
        st.session_state.last_csv_path = ""
    if "sample_fail_count" not in st.session_state:
        st.session_state.sample_fail_count = 0


init_state()
cfg = st.session_state.cfg
ap_ctrl = st.session_state.ap_ctrl
iperf_mgr = st.session_state.iperf_mgr
ports = cfg.get("iperf_servers", {}).get("ports", [5201, 5202, 5203])
capture_cfg = cfg.get("capture", {})

if "experiment_name" not in st.session_state:
    st.session_state.experiment_name = default_experiment_name()
if "notes" not in st.session_state:
    st.session_state.notes = ""
if "cwmin_exp" not in st.session_state:
    st.session_state.cwmin_exp = 4
if "cwmax_exp" not in st.session_state:
    st.session_state.cwmax_exp = 10


def do_sample() -> None:
    ok, dump_text, err = ap_ctrl.get_station_dump()
    if not ok:
        st.session_state.sample_fail_count += 1
        st.session_state.ap_online = False
        add_log(f"station dump 获取失败({st.session_state.sample_fail_count}): {err}")
        if st.session_state.sample_fail_count >= 3:
            st.session_state.sampling_active = False
            add_log("连续采样失败>=3次，已自动停止采样。请先测试 AP 连接并检查网络/SSH。")
        return

    st.session_state.sample_fail_count = 0
    st.session_state.ap_online = True

    parsed = ap_ctrl.parse_station_dump(dump_text)
    computed = compute_station_deltas(parsed, st.session_state.prev_station_map)
    ts = datetime.now().isoformat(timespec="seconds")
    exp_dir = ensure_experiment_dir(str(BASE_LOG_DIR), st.session_state.experiment_name)
    csv_path = exp_dir / "station_dump.csv"

    rows = []
    for row in computed:
        rows.append(
            {
                "timestamp": ts,
                "experiment_name": st.session_state.experiment_name,
                "cwmin_exp": st.session_state.cwmin_exp,
                "cwmax_exp": st.session_state.cwmax_exp,
                "cwmin_real": cw_real(st.session_state.cwmin_exp),
                "cwmax_real": cw_real(st.session_state.cwmax_exp),
                **row,
                "notes": st.session_state.notes,
            }
        )

    append_station_rows(csv_path, rows)
    st.session_state.latest_rows = rows
    st.session_state.history_rows.extend(rows)
    st.session_state.prev_station_map = {item["station_mac"]: item for item in parsed}
    st.session_state.last_csv_path = str(csv_path.resolve())
    add_log(f"已采样 {len(rows)} 个 station，CSV: {csv_path}")


st.title("OpenWiFi / AntSDR AP Upper Monitor")

if st.session_state.sampling_active:
    st_autorefresh(interval=int(cfg.get("sampling", {}).get("interval_sec", 1)) * 1000, key="station_autorefresh")
    do_sample()

# 第一行：实验信息 + 当前状态
left, right = st.columns([2, 1])
with left:
    st.subheader("实验信息")
    st.session_state.experiment_name = st.text_input("experiment_name", value=st.session_state.experiment_name)
    st.session_state.notes = st.text_area("notes", value=st.session_state.notes, height=100)

with right:
    st.subheader("AP 状态")
    st.write(f"AP 在线: {'✅' if st.session_state.ap_online else '❌'}")
    st.write(f"采样状态: {'🟢 运行中' if st.session_state.sampling_active else '⚪ 已停止'}")
    st.write(f"cwmin_exp={st.session_state.cwmin_exp} (CW={cw_real(st.session_state.cwmin_exp)})")
    st.write(f"cwmax_exp={st.session_state.cwmax_exp} (CW={cw_real(st.session_state.cwmax_exp)})")
    st.write(f"最近 pcap: {st.session_state.last_pcap_path or '暂无'}")
    for p in ports:
        running = iperf_mgr.get_server_status(int(p))
        st.write(f"port {p}: {'🟢 running' if running else '⚪ stopped'}")

st.markdown("---")
# 第二块：CW 参数控制
st.subheader("CW 参数区")
st.info("由于 openwifi 环境中 hostapd_cli get 不可靠，使用 monitor 网卡抓 Beacon 来验证当前 CW。")

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    st.session_state.cwmin_exp = int(st.number_input("cwmin_exp", min_value=0, max_value=15, value=int(st.session_state.cwmin_exp)))
    st.caption(f"真实 CWmin = {cw_real(st.session_state.cwmin_exp)}")
with c2:
    st.session_state.cwmax_exp = int(st.number_input("cwmax_exp", min_value=0, max_value=15, value=int(st.session_state.cwmax_exp)))
    st.caption(f"真实 CWmax = {cw_real(st.session_state.cwmax_exp)}")
with c3:
    if st.button("测试 AP 连接"):
        ok, msg = ap_ctrl.test_ap_connection()
        st.session_state.ap_online = ok
        add_log(msg)
    if st.button("设置 CW"):
        ok, msg = ap_ctrl.set_cw(st.session_state.cwmin_exp, st.session_state.cwmax_exp)
        add_log("设置 CW 成功" if ok else "设置 CW 失败")
        add_log(msg)
    if st.button("抓包验证当前 CW"):
        with st.spinner("正在创建 mon0 并抓取 1000 个包..."):
            result = ap_ctrl.capture_cw_check_pcap(
                experiment_name=st.session_state.experiment_name,
                cwmin_exp=st.session_state.cwmin_exp,
                cwmax_exp=st.session_state.cwmax_exp,
                local_base_dir=capture_cfg.get("pcap_dir", "data/pcaps"),
                monitor_iface=capture_cfg.get("monitor_iface", "mon0"),
                phy=capture_cfg.get("phy", "phy0"),
                packet_count=int(capture_cfg.get("packet_count", 1000)),
                timeout_sec=int(capture_cfg.get("timeout_sec", 60)),
            )
        if result.get("ok"):
            st.session_state.last_pcap_path = result.get("path", "")
            st.success(f"pcap 已保存：{result.get('path')}")
            st.code(
                "过滤: wlan.fc.type_subtype == 0x0008\n"
                "展开: Tagged parameters -> Vendor Specific: WMM/WME: Parameter Element -> AC_BE\n"
                "查看: ECW Min / ECW Max",
                language="text",
            )
            add_log(f"抓包验证 CW 成功: {result.get('path')}")
        else:
            st.error("抓包验证 CW 失败")
            add_log(f"抓包验证 CW 失败: {result.get('log', 'unknown error')}")

st.markdown("---")
# 第三块：监听端口管理
st.subheader("iperf3 server 监听端口管理")
server_log_dir = ensure_experiment_dir(str(BASE_LOG_DIR), st.session_state.experiment_name)

m1, m2 = st.columns(2)
with m1:
    if st.button("启动全部 server"):
        add_log(f"启动全部 server: {iperf_mgr.start_all_servers([int(x) for x in ports], str(server_log_dir))}")
with m2:
    if st.button("停止全部 server"):
        add_log(f"停止全部 server: {iperf_mgr.stop_all_servers()}")

port_cols = st.columns(max(1, len(ports)))
for idx, port in enumerate(ports):
    p = int(port)
    with port_cols[idx]:
        st.markdown(f"**port {p}**")
        st.write("running" if iperf_mgr.get_server_status(p) else "stopped")
        if st.button(f"启动 {p}"):
            ok, msg = iperf_mgr.start_server(p, str(server_log_dir / f"iperf_server_{p}.log"))
            add_log(msg)
        if st.button(f"停止 {p}"):
            ok, msg = iperf_mgr.stop_server(p)
            add_log(msg)

st.markdown("---")
# 第四块：station dump 实时监测
st.subheader("station dump 采样区")
s1, s2, s3 = st.columns(3)
with s1:
    if st.button("手动采样一次 station dump"):
        do_sample()
with s2:
    if st.button("开始 station dump 采样"):
        ok, msg = ap_ctrl.test_ap_connection()
        st.session_state.ap_online = ok
        if not ok:
            add_log(f"未开始采样：AP 不在线。{msg}")
        else:
            st.session_state.sample_fail_count = 0
            st.session_state.sampling_active = True
            add_log("已开始 station dump 采样")
            st.rerun()
with s3:
    if st.button("停止 station dump 采样"):
        st.session_state.sampling_active = False
        add_log("已停止 station dump 采样")

st.caption(f"采样间隔: {cfg.get('sampling', {}).get('interval_sec', 1)} 秒")

if st.session_state.latest_rows:
    monitor_df = pd.DataFrame(st.session_state.latest_rows)
    cols = [
        "station_mac",
        "signal",
        "signal_avg",
        "expected_throughput",
        "rx_packets",
        "rx_drop_misc",
        "tx_packets",
        "tx_retries",
        "tx_failed",
        "delta_rx_packets",
        "delta_rx_drop_misc",
        "delta_tx_packets",
        "delta_tx_retries",
        "delta_tx_failed",
        "rx_drop_rate",
        "tx_retry_rate",
        "tx_failed_rate",
    ]
    st.dataframe(monitor_df[[c for c in cols if c in monitor_df.columns]], use_container_width=True)

if st.session_state.history_rows:
    hist = pd.DataFrame(st.session_state.history_rows)
    st.line_chart(hist.pivot_table(index="timestamp", columns="station_mac", values="tx_retry_rate", aggfunc="last"))
    st.line_chart(hist.pivot_table(index="timestamp", columns="station_mac", values="tx_failed_rate", aggfunc="last"))

st.markdown("---")
# 第五块：日志区
st.subheader("日志区")

log_c1, log_c2, log_c3 = st.columns([1, 1, 2])
with log_c1:
    csv_ready = bool(st.session_state.last_csv_path) and Path(st.session_state.last_csv_path).exists()
    if csv_ready:
        csv_bytes = Path(st.session_state.last_csv_path).read_bytes()
        st.download_button(
            "导出最近 CSV",
            data=csv_bytes,
            file_name=Path(st.session_state.last_csv_path).name,
            mime="text/csv",
        )
    else:
        st.button("导出最近 CSV", disabled=True)

with log_c2:
    if st.button("一键清除日志"):
        st.session_state.logs = []
       

st.text_area("操作与错误日志", value="\n".join(st.session_state.logs[-120:]), height=260)
st.write(f"最近 CSV: {st.session_state.last_csv_path or '暂无'}")
st.write(f"最近 pcap: {st.session_state.last_pcap_path or '暂无'}")
