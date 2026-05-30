# OpenWiFi / AntSDR AP Upper Monitor

这是一个用于 **OpenWiFi / AntSDR AP 侧实验平台** 的 Streamlit 上位机软件。

本软件负责：

- 测试 Ubuntu 到 AntSDR / openwifi AP 的 SSH 连接。
- 通过 `hostapd_cli` 设置 AP 的 CW / EDCA 参数。
- 通过 monitor 网卡抓 Beacon 包，保存 pcap，用于验证当前 WMM/EDCA 参数。
- 使用 `iw dev sdr0 station dump` 对 AP 侧 station 指标做实时采样、展示、曲线可视化和 CSV 保存。
- 管理 Ubuntu 本机的 `iperf3 -s` server 监听端口，并在端口运行时实时显示类似终端的 server 输出。
- 保存实验备注、CSV、pcap 和 iperf3 server 日志。


## 运行条件

推荐环境：

- Ubuntu 20.04 虚拟机或物理机。
- Python 3.8+。
- Ubuntu 能通过 SSH 访问 AntSDR / openwifi AP。
- 浏览器可以访问 Streamlit UI。

AP 侧需要有以下命令：

- `hostapd_cli`
- `iw`
- `tcpdump`
- `ifconfig` 或 `ip`

Ubuntu 本机需要有：

- `iperf3`
- Python 依赖，见 [requirements.txt](requirements.txt)

## 网络条件

典型实验网络如下：

- Ubuntu 上位机与 SDR/AP 网络可达。
- AP 示例 IP：`192.168.10.122`。
- Ubuntu 接收端示例 IP：`192.168.10.1`。
- AP 无线接口通常是 `sdr0`。
- STA 连接 openwifi 热点。
- STA 侧向 Ubuntu 的 iperf3 server 端口发送 UDP 流，例如 `5201/5202/5203`。
- 多 STA 的连接、打流、带宽和时长由 STA 侧上位机或其他电脑控制。

## 安装步骤

克隆仓库后进入项目目录：

```bash
cd openwifi_upper_monitor_AP
```

创建并启用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

复制配置文件：

```bash
cp config.example.yaml config.yaml
```

修改 [config.yaml](config.example.yaml) 中的 AP IP、用户名、密码、接口名、抓包参数和 iperf3 server 端口。

## 配置说明

示例配置见 [config.example.yaml](config.example.yaml)：

```yaml
ap:
  host: "192.168.10.122"
  port: 22
  username: "root"
  password: "openwifi"
  # key_path: "/home/user/.ssh/id_rsa"
  interface: "sdr0"

ubuntu:
  server_ip: "192.168.10.1"

iperf_servers:
  ports: [5201, 5202, 5203]

sampling:
  interval_sec: 1

capture:
  phy: "phy0"
  monitor_iface: "mon0"
  packet_count: 1000
  pcap_dir: "data/pcaps"
  timeout_sec: 60
```

字段说明：

- `ap.host`：AntSDR / openwifi AP 的 SSH IP。
- `ap.port`：SSH 端口，默认 22。
- `ap.username` / `ap.password`：SSH 登录信息。
- `ap.key_path`：可选 SSH 私钥路径；使用私钥时可以不依赖密码。
- `ap.interface`：AP 无线接口，通常是 `sdr0`。
- `ubuntu.server_ip`：Ubuntu 本机作为接收端的 IP，仅用于记录和说明。
- `iperf_servers.ports`：本机要启动的 iperf3 server 监听端口。
- `sampling.interval_sec`：station dump 自动采样间隔。
- `capture.phy`：创建 monitor 网卡使用的 phy，例如 `phy0`。
- `capture.monitor_iface`：monitor 网卡名，例如 `mon0`。
- `capture.packet_count`：每次抓包数量，默认 1000。
- `capture.pcap_dir`：pcap 保存目录。
- `capture.timeout_sec`：抓包超时时间，避免抓不到足够包时长时间卡住。

## 启动方式

在项目目录中运行：

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

浏览器打开：

```text
http://<Ubuntu-IP>:8501
```

本机访问也可以使用：

```text
http://localhost:8501
```

## 典型实验流程

1. 启动软件。
2. 在 UI 中填写或确认 `experiment_name` 和 `notes`。
3. 点击“测试 AP 连接”，确认 Ubuntu 能 SSH 到 AP。
4. 设置 CW 参数，例如：
   - 默认窗口：`cwmin_exp=4`，`cwmax_exp=10`
   - 大窗口：`cwmin_exp=7`，`cwmax_exp=11`
5. 点击“设置 CW”。软件会执行：

   ```bash
   hostapd_cli set wmm_ac_be_cwmin <cwmin_exp>
   hostapd_cli set wmm_ac_be_cwmax <cwmax_exp>
   hostapd_cli update_beacon
   ```

6. 点击“抓包验证当前 CW”，生成 pcap。
7. 用 Wireshark 打开 pcap，查看 Beacon 中的 WMM/EDCA 参数。
8. 启动需要的 iperf3 server 端口；端口运行时，页面会显示对应端口的实时输出窗口。
9. 让 STA 侧上位机或队友电脑开始打流。
10. 点击“开始 station dump 采样”，观察实时性能曲线。
11. 实验结束后停止 station dump 采样。
12. 停止 iperf3 server。
13. 保存并整理 CSV、pcap、iperf3 日志和实验备注。

## CW 抓包验证说明

当前 openwifi 环境中，`hostapd_cli get wmm_ac_be_cwmin` 不可用，因此不能直接用 `hostapd_cli get` 查询当前 CW。

本软件采用的验证方式是：

1. 每次查询/验证前确保 monitor 网卡存在。
2. 如果没有 `mon0`，通过 SSH 在 AP 上执行类似命令：

   ```bash
   iw phy phy0 interface add mon0 type monitor
   ifconfig mon0 up
   ```

   如果 `ifconfig` 不可用或失败，则 fallback：

   ```bash
   ip link set mon0 up
   ```

3. 通过 SSH 执行 tcpdump，把 pcap 二进制流保存到 Ubuntu 本地：

   ```bash
   tcpdump -U -s 0 -i mon0 -c 1000 -w -
   ```

4. pcap 保存到：

   ```text
   data/pcaps/<experiment_name>/cw_check_<timestamp>_ecw_<cwmin>_<cwmax>.pcap
   ```

Wireshark 验证步骤：

```text
过滤: wlan.fc.type_subtype == 0x0008
展开: Tagged parameters -> Vendor Specific: WMM/WME: Parameter Element -> AC_BE
查看: ECW Min / ECW Max
```

换算关系：

```text
CW = 2^ECW - 1
```

例如 `ECW Min = 4` 对应 `CWmin = 15`。

## station dump 采样说明

采样命令：

```bash
iw dev sdr0 station dump
```

软件会解析并保存这些常用字段：

- `rx_packets`
- `rx_bytes`
- `rx_drop_misc`
- `tx_packets`
- `tx_bytes`
- `tx_retries`
- `tx_failed`
- `signal`
- `signal_avg`
- `tx_bitrate`
- `expected_throughput`

delta / rate 计算规则：

- 第一次看到某个 station 时，没有上一轮基准，因此 delta 记为 0。
- 后续采样使用相邻两次累计计数做差。
- 如果 STA 重连或计数器重置导致差值为负，软件会按 0 处理。
- `rx_throughput_mbps` / `tx_throughput_mbps` 基于相邻两次 `rx_bytes` / `tx_bytes` 差值和采样间隔估算。
- `expected_throughput_mbps` 来自 station dump 中的 `expected_throughput`，属于驱动估计值，不等同于 iperf3 实测吞吐。
- `tx_bitrate_mbps` 来自 station dump 中的 `tx_bitrate`，表示 PHY 发送速率，不等同于实际业务吞吐。
- `rx_drop_rate`、`tx_retry_rate`、`tx_failed_rate` 是相邻采样差值计算出来的比例，不是每秒速率。
- 若要当百分比理解，可以乘以 100%。

## 实时观察窗口

开启 station dump 连续采样后，页面会显示实时性能观察窗口：

- **吞吐**：`rx_throughput_mbps`、`tx_throughput_mbps`、`expected_throughput_mbps`
- **MAC 异常**：`rx_drop_rate`、`tx_retry_rate`、`tx_failed_rate`
- **链路质量**：`signal`、`signal_avg`、`tx_bitrate_mbps`

这些曲线按 station MAC 区分，适合观察 CW 参数变化、STA 打流变化或链路质量变化对 AP 侧 MAC 层指标的影响。

注意：station dump 不提供端到端时延和抖动。时延、抖动、iperf3 UDP 丢包率应从 iperf3 输出或后续专门解析逻辑中获取。

## iperf3 server 实时输出窗口

启动某个监听端口后，例如 `5201`，页面会显示该端口的实时输出窗口，内容来自：

```text
data/logs/<experiment_name>/iperf_server_5201.log
```

窗口只在对应端口运行时显示；端口停止后隐藏。这个窗口只是读取已有 iperf3 server log，不会生成额外导出文件。

## 输出文件说明

station dump CSV：

```text
data/logs/<experiment_name>/station_dump.csv
```

iperf3 server 日志：

```text
data/logs/<experiment_name>/iperf_server_<port>.log
```

CW 验证 pcap：

```text
data/pcaps/<experiment_name>/cw_check_<timestamp>_ecw_<cwmin>_<cwmax>.pcap
```

其中：

- `<experiment_name>` 来自 UI 中的实验名。
- `<timestamp>` 是抓包时刻。
- `<cwmin>` / `<cwmax>` 是 UI 中设置的 ECW 指数，不是真实 CW 值。

## Git 跟踪注意事项

以下内容是本地环境或实验输出，不应提交到 Git：

- `.venv/`
- `config.yaml`
- `data/logs/`
- `data/pcaps/`
- `*.log`
- `*.pcap`
- `*.pcapng`
- `*.csv`
- `__pycache__/`
- `*.pyc`

[.gitignore](.gitignore) 已包含这些规则。`config.yaml` 可能包含 AP 登录信息，只保留本地使用。

## 常见问题

### 为什么不能用 `hostapd_cli get wmm_ac_be_cwmin` 查询？

当前实验环境中该命令不可用或不可靠。为了确认 Beacon 中真实广播出去的 WMM/EDCA 参数，需要通过 monitor 网卡抓 Beacon 包，再用 Wireshark 或后续解析逻辑验证。

### 为什么需要 `mon0`？

普通 AP 接口通常用于正常收发数据，不适合直接抓取管理帧用于验证 Beacon。`mon0` 是 monitor 类型接口，用于抓取空口帧，包括 Beacon 中的 WMM 参数。

### 抓包卡住怎么办？

软件配置了 `capture.timeout_sec`，避免 `tcpdump -c 1000` 在抓不到足够包时无限等待。如果经常超时，可以：

- 降低 `capture.packet_count`，例如改成 100 或 200。
- 检查 `monitor_iface` 是否存在并已 up。
- 检查 `phy` 是否正确。
- 确认 AP 正在发 Beacon。
- 确认 monitor 网卡能看到 AP 所在信道。

### SSH 连不上 AP 怎么办？

检查：

- Ubuntu 是否能 ping 通 AP IP。
- [config.yaml](config.example.yaml) 中的 `ap.host`、`ap.port`、`ap.username`、`ap.password` 是否正确。
- 如果使用私钥，检查 `ap.key_path` 是否正确。
- AP 的 SSH 服务是否启动。
- 虚拟机网络模式和路由是否正确。

### `hostapd_cli set` 失败怎么办？

检查：

- AP 上 `hostapd` 是否正在运行。
- `hostapd_cli` 是否在 AP 上可用。
- 当前 openwifi 配置是否支持修改对应 WMM 参数。
- SSH 登录用户是否有执行该命令的权限。

### station dump 没有 STA 怎么办？

可能原因：

- 当前没有 STA 关联到 openwifi 热点。
- `ap.interface` 配错，常见应为 `sdr0`。
- STA 刚断开或正在重连。
- AP 侧 `iw dev sdr0 station dump` 本身没有输出。

可以先 SSH 到 AP 手动执行：

```bash
iw dev sdr0 station dump
```

确认 AP 侧原始输出。

### iperf3 server 启动失败怎么办？

检查：

- Ubuntu 是否安装了 `iperf3`。
- 端口是否被占用。
- 是否有权限启动监听端口。
- 如果某个端口异常，先在 UI 中停止该端口，再重新启动。

