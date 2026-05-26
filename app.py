from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from controllers.ap_controller import APController
from controllers.iperf_manager import IperfServerManager
from controllers.sta_controller import STAController
from utils.logger import append_csv_rows, setup_logger
from utils.parsers import compute_deltas_and_rates


st.set_page_config(page_title="OpenWiFi Upper Monitor", layout="wide")
logger = setup_logger()


def load_config(path: str = "config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_state():
    if "cfg" not in st.session_state:
        st.session_state.cfg = load_config()
    if "ap_ctrl" not in st.session_state:
        st.session_state.ap_ctrl = APController(st.session_state.cfg["ap"])
    if "sta_ctrl" not in st.session_state:
        st.session_state.sta_ctrl = STAController(
            st.session_state.cfg["stas"],
            st.session_state.cfg["ubuntu"],
            st.session_state.cfg["experiment"],
        )
    if "iperf_mgr" not in st.session_state:
        st.session_state.iperf_mgr = IperfServerManager(st.session_state.cfg["ubuntu"].get("iperf_bin", "iperf3"))
    if "logs" not in st.session_state:
        st.session_state.logs = []
    if "prev_station_map" not in st.session_state:
        st.session_state.prev_station_map = {}
    if "rows" not in st.session_state:
        st.session_state.rows = []
    if "latest_metrics" not in st.session_state:
        st.session_state.latest_metrics = []
    if "ap_online" not in st.session_state:
        st.session_state.ap_online = False
    if "sta_online" not in st.session_state:
        st.session_state.sta_online = {}
    if "cwmin_exp" not in st.session_state:
        st.session_state.cwmin_exp = 3
    if "cwmax_exp" not in st.session_state:
        st.session_state.cwmax_exp = 4


def add_log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    st.session_state.logs.append(line)
    st.session_state.logs = st.session_state.logs[-200:]
    logger.info(msg)


def poll_station_metrics():
    ok, metrics, err = st.session_state.ap_ctrl.get_station_metrics()
    if not ok:
        add_log(f"station dump 获取失败: {err}")
        return

    computed = compute_deltas_and_rates(metrics, st.session_state.prev_station_map)
    now = datetime.now().isoformat()

    rows_for_csv = []
    for item in computed:
        row = {
            "timestamp": now,
            "cwmin_exp": st.session_state.cwmin_exp,
            "cwmax_exp": st.session_state.cwmax_exp,
            "sta_mac": item.get("sta_mac"),
            "tx_packets": item.get("tx_packets"),
            "tx_retries": item.get("tx_retries"),
            "tx_failed": item.get("tx_failed"),
            "delta_tx_packets": item.get("delta_tx_packets"),
            "delta_tx_retries": item.get("delta_tx_retries"),
            "delta_tx_failed": item.get("delta_tx_failed"),
            "retry_rate": item.get("retry_rate"),
            "failed_rate": item.get("failed_rate"),
            "throughput_mbps": None,
            "jitter_ms": None,
            "loss_percent": None,
        }
        rows_for_csv.append(row)

    st.session_state.rows.extend(rows_for_csv)
    st.session_state.latest_metrics = computed
    st.session_state.prev_station_map = {x["sta_mac"]: x for x in metrics}


init_state()
cfg = st.session_state.cfg

st.title("OpenWiFi / AntSDR Upper Monitor (MVP)")

col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    st.subheader("系统状态")
    st.write(f"AP 在线: {'✅' if st.session_state.ap_online else '❌'}")
    for sta in cfg["stas"]:
        s = st.session_state.sta_online.get(sta["name"], False)
        st.write(f"{sta['name']} 在线: {'✅' if s else '❌'}")
with col_s2:
    st.subheader("iperf3 server 状态")
    server_status = st.session_state.iperf_mgr.status(cfg["ubuntu"]["iperf_ports"])
    for p, running in server_status.items():
        st.write(f"端口 {p}: {'🟢 running' if running else '⚪ stopped'}")
with col_s3:
    st.subheader("当前 CW")
    st.write(f"CWmin_exp: {st.session_state.cwmin_exp} (CW={2 ** st.session_state.cwmin_exp - 1})")
    st.write(f"CWmax_exp: {st.session_state.cwmax_exp} (CW={2 ** st.session_state.cwmax_exp - 1})")

st.markdown("---")
st.subheader("控制区")

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("连接测试"):
        ok, msg = st.session_state.ap_ctrl.test_connection()
        st.session_state.ap_online = ok
        add_log(msg)
        sta_res = st.session_state.sta_ctrl.test_all_connections()
        for n, (s, m) in sta_res.items():
            st.session_state.sta_online[n] = s
            add_log(f"{n}: {'OK' if s else 'FAIL'} {m}")

    if st.button("启动 server"):
        res = st.session_state.iperf_mgr.start_servers(cfg["ubuntu"]["iperf_ports"])
        add_log(f"启动 server: {res}")

with c2:
    if st.button("停止 server"):
        res = st.session_state.iperf_mgr.stop_servers()
        add_log(f"停止 server: {res}")

    if st.button("启动全部 STA 流量"):
        res = st.session_state.sta_ctrl.start_all()
        add_log(f"启动 STA: {res}")

with c3:
    if st.button("停止全部 STA 流量"):
        res = st.session_state.sta_ctrl.stop_all()
        add_log(f"停止 STA: {res}")

with c4:
    cwmin = st.number_input("CWmin_exp", min_value=0, max_value=15, value=st.session_state.cwmin_exp)
    cwmax = st.number_input("CWmax_exp", min_value=0, max_value=15, value=st.session_state.cwmax_exp)
    if st.button("设置 CW"):
        ok, msg = st.session_state.ap_ctrl.set_cw(int(cwmin), int(cwmax))
        if ok:
            st.session_state.cwmin_exp = int(cwmin)
            st.session_state.cwmax_exp = int(cwmax)
            add_log("设置 CW 成功")
        else:
            add_log("设置 CW 失败")
        add_log(msg)

st.markdown("---")
st.subheader("实时监测区")

if st.button("手动采样一次"):
    poll_station_metrics()
    add_log("采样完成")

latest_output = st.session_state.iperf_mgr.read_latest_output()
if latest_output:
    st.caption(f"iperf3 server 最近输出: {latest_output}")

if st.session_state.latest_metrics:
    st.dataframe(pd.DataFrame(st.session_state.latest_metrics), use_container_width=True)

if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)
    st.line_chart(df.pivot_table(index="timestamp", columns="sta_mac", values="retry_rate", aggfunc="last"))
    st.line_chart(df.pivot_table(index="timestamp", columns="sta_mac", values="failed_rate", aggfunc="last"))

st.markdown("---")
st.subheader("日志区")
log_text = "\n".join(st.session_state.logs[-80:]) if st.session_state.logs else ""
st.text_area("最近执行日志", value=log_text, height=220)

csv_dir = Path(cfg["experiment"].get("csv_dir", "data/logs"))
csv_name = cfg["experiment"].get("csv_filename", "experiment_log.csv")
csv_path = csv_dir / csv_name

if st.button("保存实验 CSV"):
    append_csv_rows(str(csv_path), st.session_state.rows)
    add_log(f"CSV 已保存: {csv_path}")

st.caption("提示：MVP 先支持手动采样。后续可扩展为自动定时刷新。")
