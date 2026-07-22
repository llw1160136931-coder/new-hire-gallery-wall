# 新员工展示墙并发压测程序

这套工具用程序模拟真实用户，不需要真的找 100 个人。它覆盖首页、分页作品列表与详情、搜索、课程、标签、排行榜、登录、点赞、投票、图片上传、8 MiB 分片视频上传、图片下载和视频 Range 播放，并同时采集服务器 CPU、内存、磁盘与进程数据。作品列表响应会严格校验分页元数据，避免退化为一次返回全部作品。

## 先看安全规则

- **禁止对 `https://xinhuowall.com` 或 `https://www.xinhuowall.com` 做写入压测。** `run_suite.py` 和 `locustfile.py` 都会拦截，且没有绕过开关。
- 对非测试域名做只读压测也会默认拦截；只有明确传入 `--allow-production-read-only READ_ONLY` 才能启动。正式的 100 人验收仍应在隔离压测域名完成。
- 写入压测只能指向主机名明确带 `loadtest`、`test`、`staging`、`stage`、`qa` 或 `preprod` 的隔离环境，例如 `https://loadtest.xinhuowall.com`。
- 隔离环境必须使用独立的 PostgreSQL 数据库、媒体目录和上传分片目录。不要复用正式数据库。
- 压测机与被测服务器应是两台机器。若 Locust 跑在被测服务器上，CPU、内存结果会失真。
- 同一台云服务器承载正式站和压测站时，重压仍可能拖慢正式站，只能在维护时段进行；最可靠的做法是临时克隆一台同配置腾讯云服务器。
- 凭据 CSV 含随机测试密码，已被 `.gitignore` 排除；用完仍应立即删除。

## 工具组成

| 文件 | 用途 |
| --- | --- |
| `locustfile.py` | 模拟用户行为并严格校验 HTTP、Range、上传响应和 SHA-256 |
| `run_suite.py` | 一键执行分阶段压测，输出 Locust CSV、HTML、日志和套件元数据 |
| `generate_fixtures.py` | 生成合法 JPEG 与 MP4 上传素材及 `assets.csv` |
| `server_monitor.py` | 每秒记录 CPU、内存、磁盘、网络、Gunicorn、Nginx、PostgreSQL |
| `analyze_results.py` | 生成中文 Markdown/JSON 验收报告，防止零请求或未到 100 人时假通过 |
| `prepare_load_test` | 在独立数据库创建随机账号、200 个作品、30 门课程、媒体和标签 |
| `verify_load_test` | 只读核对点赞/投票、上传文件、视频 SHA-256 和分片残留 |
| `cleanup_load_test` | 清理固定 `loadtest_` 范围内的测试数据与文件 |

## 四档场景

| 预设 | 最大用户 | 默认时长 | 作用 |
| --- | ---: | ---: | --- |
| `smoke` | 5 | 2 分钟 | 先确认登录、浏览、互动、图片和视频上传链路可用 |
| `target100` | 100 | 约 62 分钟 | 25→50→75→100 人渐进，含混合使用与上传尖峰 |
| `upload100` | 100 | 30 分钟 | 100 个真实上传用户，每人最多传 1 组图片和 1 个视频 |
| `full` | 200 | 约 4 小时 12 分钟 | 包含以上场景、100 人长稳测试及 125/150/200 人找极限 |

`upload100` 使用默认 50/100 MiB 视频时，可能产生约 5–10 GiB 网络与磁盘写入。执行前先确认测试服务器磁盘、带宽和腾讯云流量费用。

## 1. 准备隔离压测环境

下面只是变量示例，密码继续放在服务器受保护的环境文件中，不要写进 Git：

```bash
DJANGO_ENV=production
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=loadtest.xinhuowall.com,127.0.0.1,localhost
DJANGO_CORS_ALLOWED_ORIGINS=https://loadtest.xinhuowall.com
DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=new_hire_gallery_loadtest
DJANGO_DB_USER=<独立压测数据库用户>
DJANGO_DB_PASSWORD=<独立强密码>
DJANGO_DB_HOST=127.0.0.1
DJANGO_DB_PORT=5432
DJANGO_MEDIA_ROOT=/var/lib/new-hire-gallery-loadtest/media
DJANGO_WORK_UPLOAD_CHUNK_DIR=/var/lib/new-hire-gallery-loadtest/media/upload_chunks
COURSE_MATERIAL_ROOT=/var/lib/new-hire-gallery-loadtest/course-files
DJANGO_LOADTEST_MODE=true
LOADTEST_TARGET_ID=xinhuowall-loadtest-20260717
DRF_ANON_THROTTLE_RATE=100000/min
DRF_USER_THROTTLE_RATE=100000/min
DRF_LOGIN_THROTTLE_RATE=10000/min
DRF_UPLOAD_THROTTLE_RATE=100000/min
DRF_SEARCH_THROTTLE_RATE=100000/min
```

`LOADTEST_TARGET_ID` 不是密码，但必须只在这套隔离后端中配置，并与压测机命令中的 `--target-id` 完全一致。正式服务应保持 `DJANGO_LOADTEST_MODE=false`（或不配置），也不能使用 `loadtest_camp` 作为当前培训期。

压测实例使用单独的 Gunicorn 端口和 systemd 服务，并让 `loadtest.xinhuowall.com` 的 Nginx 反向代理到该端口。配置完成后，在压测环境执行：

容量测试时提高的是隔离环境限流值，否则同一台压测机的匿名请求会共享 IP 配额，测试到的只是 429 限流而不是服务器容量。另行保留一次默认限流配置的专项测试即可。压测域名必须经过与正式站相同的 Nginx 静态首页、媒体文件和 Range 配置，不要直接对 Django `runserver` 下结论。

```bash
sudo bash -c '
set -a
source /etc/new-hire-gallery-loadtest.env
set +a
cd /opt/new-hire-gallery/backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py prepare_load_test \
  --users 100 \
  --targets 200 \
  --image-size-mib 2 \
  --video-size-mib 50 \
  --output /tmp/loadtest-accounts.csv
'
sudo chown ubuntu:ubuntu /tmp/loadtest-accounts.csv
sudo chmod 600 /tmp/loadtest-accounts.csv
```

`full` 的 200 人阶段需要把 `--users` 改为 `200`。命令只有在数据库名称包含 `loadtest` 时才会创建数据。默认 200 个作品会生成约 120 MiB 已审核图片和 1 GiB 已审核视频，让浏览压测也会真实读取大文件；准备前建议至少预留 3 GiB 空间。

把 `/tmp/loadtest-accounts.csv` 安全复制到压测机，确认复制成功后删除服务器上的副本。不要在聊天、截图或 GitHub 中粘贴该文件内容。

## 2. 在独立压测机安装依赖并生成素材

Windows PowerShell 示例：

```powershell
cd "C:\path\to\new-hire-gallery"
py -m venv .venv-load
.\.venv-load\Scripts\python.exe -m pip install -r .\backend\load_tests\requirements.txt

.\.venv-load\Scripts\python.exe .\backend\load_tests\generate_fixtures.py `
  --output-dir C:\loadtest\fixtures `
  --image-mib 2,5 `
  --video-mib 50,100
```

生成的简化 MP4 用于上传吞吐和文件签名测试；若还要人工确认浏览器播放，请增加 `--video-source C:\path\to\real-test-video.mp4`。

## 3. 先做命令预检，再做 5 人冒烟

```powershell
.\.venv-load\Scripts\python.exe .\backend\load_tests\run_suite.py `
  --host https://loadtest.xinhuowall.com `
  --credentials C:\loadtest\loadtest-accounts.csv `
  --assets C:\loadtest\fixtures\assets.csv `
  --preset smoke `
  --confirm-writes LOADTEST_ONLY `
  --target-id xinhuowall-loadtest-20260717 `
  --dry-run
```

确认输出中的域名、账号数和命令都正确，再去掉 `--dry-run`。冒烟测试不通过时不要继续加压。

## 4. 同时启动服务器监控

在被测服务器另开一个终端。冒烟阶段默认 120 秒，可监控 150 秒：

```bash
cd /opt/new-hire-gallery
source backend/.venv/bin/activate
python backend/load_tests/server_monitor.py \
  --output /tmp/smoke-monitor.jsonl \
  --duration 150 \
  --interval 1 \
  --disk-path /var/lib/new-hire-gallery-loadtest \
  --process-name gunicorn \
  --process-name nginx \
  --process-name postgres
```

先启动监控，再立即启动 Locust。正式的 100 人阶段建议逐个运行 `--phase`，这样每个阶段有独立监控文件。例如 `mixed-100` 默认 1800 秒：

```powershell
.\.venv-load\Scripts\python.exe .\backend\load_tests\run_suite.py `
  --host https://loadtest.xinhuowall.com `
  --credentials C:\loadtest\loadtest-accounts.csv `
  --assets C:\loadtest\fixtures\assets.csv `
  --preset target100 `
  --phase mixed-100 `
  --confirm-writes LOADTEST_ONLY `
  --target-id xinhuowall-loadtest-20260717
```

需要专门验证 100 人同时上传时，先确认至少 12 GiB 可用空间，再执行 `--preset upload100`。

## 5. 生成性能验收报告

把服务器监控 JSONL 复制回压测机。以下示例中的 Locust 文件前缀，以实际结果目录为准：

```powershell
.\.venv-load\Scripts\python.exe .\backend\load_tests\analyze_results.py `
  --locust-stats C:\loadtest\results\mixed-100_stats.csv `
  --locust-history C:\loadtest\results\mixed-100_stats_history.csv `
  --locust-failures C:\loadtest\results\mixed-100_failures.csv `
  --monitor C:\loadtest\results\mixed-100-monitor.jsonl `
  --output-md C:\loadtest\results\mixed-100-report.md `
  --output-json C:\loadtest\results\mixed-100-report.json `
  --expected-users 100 `
  --expected-duration-seconds 1800 `
  --min-requests 1000 `
  --max-error-rate 1 `
  --max-p95-ms 2000 `
  --max-cpu 90 `
  --max-memory 85 `
  --max-disk-usage 85 `
  --max-disk-busy 90 `
  --expected-monitor-host VM-0-9-ubuntu `
  --fail-on-threshold
```

程序在以下任一情况都会判定失败：没有请求、没真正达到目标用户数、Locust 与服务器监控的有效重叠时间不足 90%、监控主机名不匹配、Gunicorn/Nginx/PostgreSQL 关键进程缺失、错误率或 P95 超标、CPU/内存/磁盘超标、监控字段缺失。`--expected-monitor-host` 填服务器执行 `hostname` 的输出；如果服务器使用其他进程（例如 Uvicorn），可重复传入 `--required-process uvicorn` 等参数来明确替换默认进程列表。

## 6. 核对业务数据是否正确

性能没有报错不代表业务一定正确。压测结束、清理之前，在压测服务器执行只读核验：

```bash
sudo bash -c '
set -a
source /etc/new-hire-gallery-loadtest.env
set +a
cd /opt/new-hire-gallery/backend
.venv/bin/python manage.py verify_load_test \
  --output /tmp/loadtest-verification.json \
  --expected-users 100 \
  --expected-seed-targets 200 \
  --min-likes 1 \
  --min-votes 1 \
  --min-uploaded-image-works 1 \
  --min-uploaded-video-works 1
'
```

它会核对点赞/投票是否重复或丢失、作品计数是否一致、上传文件是否存在且非空、视频最终 SHA-256 是否一致，以及是否留下未完成分片。只有性能报告和这个一致性报告都为 `PASS`，本轮测试才算通过。

## 7. 清理

保存好脱敏报告后，在压测环境执行：

```bash
sudo bash -c '
set -a
source /etc/new-hire-gallery-loadtest.env
set +a
cd /opt/new-hire-gallery/backend
.venv/bin/python manage.py cleanup_load_test
rm -f /tmp/loadtest-accounts.csv
'
```

压测机也要删除账号 CSV 和不再需要的大素材。清理命令只允许连接名称包含 `loadtest` 的数据库，并且只删除固定压测前缀对应的数据和文件。

## 如何用大白话判断结果

- `PASS`：这次设定的压力下，100 人确实都上线了，页面和上传没有明显错误，响应速度、服务器资源和数据库结果都在阈值内。
- `FAIL`：不是等于“系统一定会崩”，而是至少有一项达不到上线标准；先看报告中失败的那一行，再定位是慢、报错、资源满、上传损坏还是业务数据不一致。
- 一次通过不代表永远安全。代码、数据库数据量、云服务器配置变化后都要重测，至少保留冒烟、100 人混合、100 人上传三份结果。

旧的单文件 `run_load_test.py` 已停用，避免固定测试密码或旧流程被误用；压测统一使用本页的 Locust 套件。
