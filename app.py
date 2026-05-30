from datetime import datetime
from html import escape
from pathlib import Path
from typing import List

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml
from streamlit.components.v1 import html
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


def read_log_tail(log_path: Path, max_lines: int = 240) -> str:
    if not log_path.exists():
        return "等待 iperf3 输出..."
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines:
        return "等待 iperf3 输出..."
    return "\n".join(lines[-max_lines:])


def render_terminal(title: str, content: str, height: int = 420) -> None:
    safe_title = escape(title)
    safe_content = escape(content)
    html(
        f"""
        <div style="font-family: monospace; border: 1px solid #3a3a3a; border-radius: 6px; background: #0e1117; color: #fafafa;">
          <div style="padding: 8px 12px; border-bottom: 1px solid #3a3a3a; color: #9cdcfe; font-weight: 600;">
            {safe_title}
          </div>
          <pre id="terminal-output" style="height: {height}px; overflow-y: auto; margin: 0; padding: 12px; white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.45;">{safe_content}</pre>
        </div>
        <script>
          const output = document.getElementById("terminal-output");
          output.scrollTop = output.scrollHeight;
        </script>
        """,
        height=height + 54,
    )


def render_metric_card(label: str, value: str, help_text: str) -> None:
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;background:#ffffff;box-shadow:0 1px 2px rgba(0,0,0,0.04);">
          <div style="font-size:13px;color:#64748b;margin-bottom:6px;">{escape(label)}</div>
          <div style="font-size:26px;font-weight:700;color:#0f172a;">{escape(value)}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px;">{escape(help_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_line_chart(df: pd.DataFrame, fields: List[str], title: str, y_label: str) -> None:
    available = [field for field in fields if field in df.columns]
    if not available:
        st.info(f"暂无 {title} 数据")
        return
    chart_df = df[["timestamp", "station_mac", *available]].copy()
    long_df = chart_df.melt(id_vars=["timestamp", "station_mac"], value_vars=available, var_name="metric", value_name="value")
    long_df = long_df.dropna(subset=["value"])
    if long_df.empty:
        st.info(f"暂无 {title} 数据")
        return
    long_df["series"] = long_df["station_mac"] + " · " + long_df["metric"]
    fig = px.line(long_df, x="timestamp", y="value", color="series", markers=True, title=title)
    fig.update_layout(height=330, margin=dict(l=20, r=20, t=48, b=20), yaxis_title=y_label, xaxis_title="时间")
    st.plotly_chart(fig, use_container_width=True)


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
    sampling_interval = float(cfg.get("sampling", {}).get("interval_sec", 1))
    computed = compute_station_deltas(parsed, st.session_state.prev_station_map, sampling_interval)
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
elif any(iperf_mgr.get_server_status(int(p)) for p in ports):
    st_autorefresh(interval=1000, key="iperf_log_autorefresh")

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
st.caption("这里只管理 Ubuntu 本机的 iperf3 -s 监听端口；STA 侧打流由队友的 STA 上位机或各自电脑完成。")
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
    running = iperf_mgr.get_server_status(p)
    with port_cols[idx]:
        st.markdown(f"**port {p}**")
        st.write("running" if running else "stopped")
        if st.button(f"启动 {p}"):
            ok, msg = iperf_mgr.start_server(p, str(server_log_dir / f"iperf_server_{p}.log"))
            add_log(msg)
            st.rerun()
        if st.button(f"停止 {p}"):
            ok, msg = iperf_mgr.stop_server(p)
            add_log(msg)
            st.rerun()

for port in ports:
    p = int(port)
    if iperf_mgr.get_server_status(p):
        log_path = server_log_dir / f"iperf_server_{p}.log"
        render_terminal(f"port {p} 实时输出", read_log_tail(log_path))

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
st.caption("rx_drop_rate / tx_retry_rate / tx_failed_rate 是相邻两次 station dump 计数差计算出的比例，不是每秒速率。第一次采样的 delta 记为 0。")

if st.session_state.latest_rows:
    monitor_df = pd.DataFrame(st.session_state.latest_rows)
    latest_total_rx = monitor_df.get("rx_throughput_mbps", pd.Series(dtype=float)).sum()
    latest_total_tx = monitor_df.get("tx_throughput_mbps", pd.Series(dtype=float)).sum()
    latest_retry = monitor_df.get("tx_retry_rate", pd.Series(dtype=float)).mean()
    latest_signal = monitor_df.get("signal_avg", pd.Series(dtype=float)).mean()

    card1, card2, card3, card4 = st.columns(4)
    with card1:
        render_metric_card("RX 吞吐", f"{latest_total_rx:.2f} Mbps", "STA → AP 当前总量")
    with card2:
        render_metric_card("TX 吞吐", f"{latest_total_tx:.2f} Mbps", "AP → STA 当前总量")
    with card3:
        render_metric_card("平均重传", f"{latest_retry:.3f}", "TX retries / packet")
    with card4:
        signal_text = "--" if pd.isna(latest_signal) else f"{latest_signal:.0f} dBm"
        render_metric_card("平均信号", signal_text, "signal_avg")

    cols = [
        "station_mac",
        "signal",
        "signal_avg",
        "tx_bitrate",
        "expected_throughput",
        "rx_throughput_mbps",
        "tx_throughput_mbps",
        "expected_throughput_mbps",
        "tx_bitrate_mbps",
        "rx_packets",
        "rx_bytes",
        "rx_drop_misc",
        "tx_packets",
        "tx_bytes",
        "tx_retries",
        "tx_failed",
        "delta_rx_packets",
        "delta_rx_bytes",
        "delta_rx_drop_misc",
        "delta_tx_packets",
        "delta_tx_bytes",
        "delta_tx_retries",
        "delta_tx_failed",
        "rx_drop_rate",
        "tx_retry_rate",
        "tx_failed_rate",
    ]
    with st.expander("查看最新 station dump 明细", expanded=False):
        st.dataframe(monitor_df[[c for c in cols if c in monitor_df.columns]], use_container_width=True)
else:
    st.info("暂无 station dump 数据。点击手动采样一次，或开始连续采样后会显示实时性能观察窗口。")

st.subheader("实时性能观察窗口")
if st.session_state.history_rows:
    hist = pd.DataFrame(st.session_state.history_rows)
    tabs = st.tabs(["吞吐", "MAC 异常", "链路质量"])
    with tabs[0]:
        st.caption("基于相邻两次 station dump 的 byte delta 估算；expected throughput 是驱动估计值。")
        render_line_chart(hist, ["rx_throughput_mbps", "tx_throughput_mbps", "expected_throughput_mbps"], "吞吐实时变化", "Mbps")
    with tabs[1]:
        st.caption("这些是 AP/MAC 层计数比例，不等同于 iperf3 端到端丢包率。")
        render_line_chart(hist, ["rx_drop_rate", "tx_retry_rate", "tx_failed_rate"], "MAC 层异常实时变化", "ratio")
    with tabs[2]:
        st.caption("用于判断性能变化是否由链路质量或 PHY 速率变化引起。")
        render_line_chart(hist, ["signal", "signal_avg", "tx_bitrate_mbps"], "链路质量实时变化", "dBm / Mbps")
else:
    st.info("连续采样开始后，这里会显示吞吐、重传/失败、信号质量的实时曲线。")

st.markdown("---")
# 第五块：日志区
st.subheader("日志区")

if st.button("一键清除日志"):
    st.session_state.logs = []


st.text_area("操作与错误日志", value="\n".join(st.session_state.logs[-120:]), height=260)
st.write(f"最近 CSV: {st.session_state.last_csv_path or '暂无'}")
st.write(f"最近 pcap: {st.session_state.last_pcap_path or '暂无'}")
