# 使用说明（AP 上位机）

## 软件边界

本软件仅用于 AP 上位机，不负责 STA 打流控制，不生成 STA 打流参数。

负责内容：
- AP CW 参数设置
- AP 侧 station dump 采样
- Ubuntu iperf3 server 监听端口管理
- 抓包验证 CW（Beacon/WMM）
- 日志、CSV、pcap 保存

## 推荐流程

1. 修改 `config.yaml`
2. 启动 UI
3. 点击“测试 AP 连接”
4. 设置 `cwmin_exp/cwmax_exp`
5. 启动全部 iperf3 server 端口
6. 开始 station dump 采样
7. 队友在各自 STA 端启动打流
8. 必要时点击“抓包验证当前 CW”并用 Wireshark 验证
9. 实验结束后停止采样、停止 server
10. 查看：
   - `data/logs/<experiment_name>/station_dump.csv`
   - `data/logs/<experiment_name>/iperf_server_<port>.log`
   - `data/pcaps/<experiment_name>/*.pcap`

## Wireshark 验证 CW

过滤：

```text
wlan.fc.type_subtype == 0x0008
```

展开：

```text
Tagged parameters -> Vendor Specific: WMM/WME: Parameter Element -> AC_BE
```

查看：
- `ECW Min`
- `ECW Max`

换算：

```text
CW = 2^ECW - 1
```
