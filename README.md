# Streamlit 服务器数据分析平台

面向内部团队的服务器数据分析平台。用户在浏览器中直接选择 Linux 服务器上的 MAT/BIN 数据，完成波形预览、FFT、带通滤波和小波包能量分析，并下载 PNG、PDF、CSV 结果。

## 已实现

- Argon2 密码登录、管理员与分析人员角色
- SQLite 用户、数据索引、任务、结果和审计日志
- 受控数据根目录与路径穿越防护
- MAT v5、MAT v7.3/HDF5 和特定 56 字节头 BIN 格式
- 长波形 min/max 下采样预览
- 原始波形、FFT 幅值谱、带通滤波、小波包能量
- 左侧分析方法、中间绘图大屏、右侧 8/2 通道文件选择器
- 默认 8+2 业务通道栏，切换方法、文件或通道后自动刷新
- Linux 文件事件监听：新数据写入稳定后自动加入索引，页面仅在索引变化时更新
- Welch 功率谱、信号包络以及顶部图片/数据保存
- 任务参数、算法版本、状态和结果追溯
- PNG、PDF、CSV、JSON 结果文件
- Streamlit 多页面界面、Docker Compose 与 Nginx

## 本地启动

要求 Python 3.12 或 3.13。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
python scripts\generate_demo_data.py
streamlit run app.py
```

浏览器打开 `http://localhost:8501`。首次启动时页面会要求创建管理员，密码至少 10 位。

## 配置真实数据目录

编辑 `.env`：

```dotenv
DATA_ROOTS=D:\data\collection;E:\other-data
```

多个目录使用分号分隔。平台只读取 `.mat` 和 `.bin` 文件，并在读取前再次检查文件是否位于允许根目录。

## Windows 算法端读取 SFTP 数据

平台可以只在 Windows 电脑运行算法和网页，通过 SFTP 索引 Linux 数据服务器，不需要映射盘符。
在本机 `.env` 中配置（不要提交密码或私钥口令）：

```dotenv
SFTP_ENABLED=true
SFTP_HOST=192.168.31.201
SFTP_PORT=22
SFTP_USERNAME=Inspur
SFTP_PASSWORD=
SFTP_PRIVATE_KEY_PATH=C:/Users/你的用户名/.ssh/id_ed25519
SFTP_REMOTE_ROOT=/data/usershare/test-manager/datas
SFTP_SYNC_SECONDS=30
SFTP_CACHE_TTL_HOURS=24
SFTP_CACHE_MAX_GB=20
```

启动网页和远程索引进程：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\windows\start-platform.ps1
```

停止两个进程：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\windows\stop-platform.ps1
```

远程目录和文件名会写入本地 SQLite 索引。BIN 索引只读取 56 字节文件头；MAT 在首次
选择时下载并解析。完整原始文件仅在真正分析时进入 `var/cache/sftp` 临时缓存，并按
`SFTP_CACHE_TTL_HOURS` 和 `SFTP_CACHE_MAX_GB` 自动清理。SFTP 主机密钥默认必须已经存在于
当前 Windows 用户的 `~/.ssh/known_hosts` 中。

## 测试

```powershell
pytest -q
```

## Linux Docker 部署

1. 复制 `.env.example` 为 `.env`，设置生产参数。
2. 设置服务器原始数据目录：

```bash
export HOST_DATA_ROOT=/srv/acquisition/raw
docker compose up -d --build
```

3. 内网访问 `http://服务器地址:8080`。

Compose 将原始目录只读挂载到 `/data/raw`。正式上线前应配置内网/VPN、防火墙以及 Nginx HTTPS 证书，不要直接向公网暴露 8501 端口。

服务器没有 Docker 或管理员权限时，可以使用用户级部署脚本：

```bash
DATA_ROOT=/srv/acquisition/raw SERVICE_HOST=127.0.0.1 SERVICE_PORT=8501 \
  bash deploy/server/install-user.sh ~/streamlit-analysis-platform.tar
```

脚本会安装隔离的 Python 3.12 环境，创建用户级 systemd 服务，并将运行状态保存在代码目录之外。
部署脚本同时启用 `streamlit-analysis-watcher.service`。监听器递归监控数据目录，
默认等待文件稳定 5 秒后入库，并每 300 秒补偿扫描一次；这两个间隔可通过
`AUTO_INDEX_STABLE_SECONDS` 和 `AUTO_INDEX_RECONCILE_SECONDS` 调整。

## BIN 格式

当前解析器兼容现有脚本使用的格式：

- 文件头 56 字节
- 0～31：设备名
- 32～39：小端 uint64 时间戳（毫秒）
- 40～43：小端 uint32 通道数
- 44～47：小端 uint32 采样率
- 48～51：小端 uint32 每通道采样数
- 56 字节后：按采样点和通道交错排列的小端 float64

## 安全边界

- 原始数据应以只读权限提供给应用。
- `.env`、数据库、结果、原始数据和密钥不会提交到 Git。
- 页面不能执行用户提供的 Python、Shell 或 SQL。
- SQLite 适合当前少量内部用户；并发和权限需求增长后应迁移 PostgreSQL。
- 典型任务超过 30～60 秒或多人并发时，应增加独立任务队列。

## 项目文档

实施方案见 `docs/Streamlit数据分析平台项目计划书.md`。
