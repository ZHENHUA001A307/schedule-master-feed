# Schedule Master Feed

日常内务循环提醒的 RSS 生成系统。

- 每天 UTC 0:00（北京 08:00）由 GitHub Actions 运行 `src/main.py`
- 读取 `config/schedule.yml`，按「周期 + 偏移」判断今天到期任务
- 生成 `feed.xml`，RSS 阅读器订阅
- 本地 WebUI 编辑 `schedule.yml`，端口 8766

## 快速开始

```bash
python -m pip install -r requirements.txt
python webui/server.py