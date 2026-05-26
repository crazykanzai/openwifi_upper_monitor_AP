# openwifi_upper_monitor (MVP)

面向 openwifi/AntSDR 实验平台的 Ubuntu 上位机最小可用监测与控制软件（Streamlit + Python）。

## 功能范围（MVP）

- 读取 `config.yaml` 中 AP/STA/Ubuntu 配置
- 通过 SSH 控制 AP、STA
- AP 侧：
  - 连通性测试
  - 拉取 `iw dev sdr0 station dump`
  - 解析 `tx packets / tx retries / tx failed / signal`
  - 计算 `retry_rate` 与 `failed_rate`
  - 设置 CW 参数：`wmm_ac_be_cwmin/cwmax` 并 `update_beacon`
- STA 侧：
  - 单台/全部连接测试
  - 单台/全部启动 iperf3 UDP client
  - 单台/全部停止 iperf3
- Ubuntu 本机：
  - 一键启动/停止多个 iperf3 server
  - 捕获 server 标准输出（第一版不强依赖解析）
- Streamlit 页面：
  - 状态区、控制区、实时监测区、日志区
  - CSV 数据落盘

---

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 修改配置

编辑 `config.yaml`，替换以下占位符：

- `ap.host / username / password 或 key_path`
- `stas[*].host / username / password 或 key_path`
- `ubuntu.server_ip`

> 不要把真实密码提交到 Git 仓库。

## 3. 运行

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

宿主机浏览器访问：

```text
http://<Ubuntu_VM_IP>:8501
```

---

## 4. 模块说明

- `controllers/ap_controller.py`：AP 连接、station dump、CW 设置
- `controllers/sta_controller.py`：STA 启停 iperf3 client
- `controllers/iperf_manager.py`：本机 iperf3 server 进程管理
- `utils/parsers.py`：station dump 解析、delta/rate 计算
- `utils/logger.py`：日志与 CSV 记录

---

## 5. 快速手动测试

1. 点击 **连接测试**，确认 AP/STA 在线状态。
2. 点击 **启动 server**，确认 5201/5202/5203 正常监听。
3. 点击 **启动全部 STA 流量**。
4. 观察实时监测区中 STA 的 `tx packets/retries/failed` 与曲线变化。
5. 调整 `CWmin_exp/CWmax_exp` 后点击 **设置 CW**。
6. 点击 **保存实验 CSV**。
7. 点击 **停止全部 STA 流量**、**停止 server**。

---

## 6. 说明

- 当前版本优先保证流程跑通，未引入 AI/强化学习。
- 若 `station dump` 字段格式因驱动版本差异变化，可在 `utils/parsers.py` 调整正则。
