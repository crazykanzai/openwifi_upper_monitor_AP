# OpenWiFi / AntSDR AP Upper Monitor

本软件定位为 **AP 上位机**，只负责：

- AP 参数控制（CW 设置）
- AP 侧监测（station dump 采样与可视化）
- Ubuntu 本机 iperf3 server 监听端口管理
- 抓包验证 CW（monitor 网卡 + Beacon/WMM）
- 实验日志、CSV、pcap 保存

> STA 打流由队友的 STA 上位机或各自电脑完成。  
> 本软件不负责 STA 带宽、时长、payload length，也不控制 STA 数量。

## 功能模块

1. **实验信息区**
   - `experiment_name`
   - `notes`

2. **CW 参数区**
   - `cwmin_exp` / `cwmax_exp`
   - 实时显示真实 CW：`CW = 2^ECW - 1`
   - `设置 CW`
   - `抓包验证当前 CW`

3. **AP 状态区**
   - AP 在线/离线
   - station dump 采样状态
   - 当前 CW 指数与真实 CW
   - 最近一次 pcap 保存路径
   - iperf3 server 端口状态

4. **iperf3 server 监听端口管理**
   - 默认端口来自 `config.yaml`（如 `[5201, 5202, 5203]`）
   - 启动全部 / 停止全部
   - 单端口启动 / 停止
   - 日志：`data/logs/<experiment_name>/iperf_server_<port>.log`

5. **station dump 采样区**
   - 手动采样一次
   - 开始采样
   - 停止采样
   - 采样间隔来自 `config.yaml`（默认 1 秒）
   - CSV 自动保存：`data/logs/<experiment_name>/station_dump.csv`

6. **日志区**
   - 操作日志
   - 错误日志
   - 最近保存 CSV 路径
   - 最近保存 pcap 路径

## 抓包验证当前 CW（Wireshark）

点击“抓包验证当前 CW”后，程序将：

1. 通过 SSH 连接 SDR/AP
2. 确保 monitor 接口存在：
   - 若不存在：`iw phy phy0 interface add mon0 type monitor`
3. 启动接口：
   - `ifconfig mon0 up`
   - 若失败回退：`ip link set mon0 up`
4. 抓包：`tcpdump -i mon0 -c 1000 -w -`
5. 将二进制 pcap 保存到本地：
   - `data/pcaps/<experiment_name>/cw_check_<timestamp>_ecw_<cwmin>_<cwmax>.pcap`

Wireshark 验证步骤：

- 过滤：`wlan.fc.type_subtype == 0x0008`
- 找到 AP Beacon 帧
- 展开：`Tagged parameters -> Vendor Specific: WMM/WME: Parameter Element -> AC_BE`
- 查看：`ECW Min / ECW Max`
- 换算真实 CW：`CW = 2^ECW - 1`

## 配置示例

```yaml
ap:
  host: "192.168.10.122"
  username: "root"
  password: "openwifi"
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

## 协同实验流程

1. AP 上位机设置 CW
2. AP 上位机启动 iperf3 server 端口
3. AP 上位机开始 station dump 采样
4. 队友在 STA 上位机启动打流
5. 实验结束后 AP 上位机停止采样并查看日志

## 运行

```bash
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
