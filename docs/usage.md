# 使用说明（MVP）

## 启动前检查

- Ubuntu 20.04 已安装 Python3、pip、iperf3
- AP 与 3 台 STA 可 SSH 登录
- Ubuntu 与 AP/STA 网络互通

## 操作流程

1. 安装依赖：`pip install -r requirements.txt`
2. 修改 `config.yaml`
3. 启动 Web UI：`streamlit run app.py --server.address 0.0.0.0 --server.port 8501`
4. 在 UI 中执行：
   - 连接测试
   - 启动 server
   - 启动全部 STA 流量
   - 观察 station dump 与曲线
   - 设置 CW 并继续观测
   - 保存 CSV

## 故障排查

- SSH 失败：检查 IP、防火墙、账号密码/密钥、端口
- `hostapd_cli` 执行失败：检查 AP 权限与 hostapd 环境
- `iperf3` 未找到：确认 Ubuntu/STA 已安装 iperf3
- 曲线无数据：确认 STA 已成功关联 AP 且有 UDP 流量
