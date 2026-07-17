# 新员工展示墙系统

一个 Vite + React + Django REST Framework 项目，用于新员工培训作品展示、课程安排、分时段签到、点赞投票与管理员审核。

## 运行方式

安装依赖：

```powershell
npm install
```

启动开发服务：

```powershell
npm run dev
```

前端默认连接：

```text
http://127.0.0.1:8001/api
```

如需改地址，可以在前端环境变量中设置：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8001/api"
npm run dev
```

## 功能

- 学员发布培训作品或 AI 作品，支持上传图片、PDF、视频文件，也支持填写图片地址和作品链接。
- 作品文件采用后端切片上传流程，最大支持 500MB，避免大文件一次性上传失败。
- 新作品默认进入待审核状态。
- 管理员可在审核中心通过或打回作品。
- 被打回的作品会显示打回原因，学员可修改后重新提交审核。
- 通过审核的作品展示在作品墙，支持点赞和投票。
- 首页搜索作品/同学时，会请求 Django 后端搜索接口，不走前端本地过滤。
- 首页课程表自动区分已结束、进行中、未开始。
- 管理员可为课程上传 1 张思维导图和多份 PDF/PPTX 资料；学员可在课程详情中放大查看思维导图、在线查看 PDF 或下载 PPTX。
- 学员可在三个固定时段使用 4 位签到码签到，管理员可生成签到码并查看已签到、未签到数据。
- 个人中心支持编辑姓名、头像、工作单位、MBTI、星座和性别。

当前版本的 React 前端已接入 Django API，登录使用限时 JWT access token，并在过期时尝试用 refresh token 自动续期。

## 后端开发

后端使用 Django + Django REST Framework，本地开发数据库已切换为 PostgreSQL 17。当前电脑使用项目专用实例 `127.0.0.1:55432/new_hire_gallery`，原 SQLite 文件只作为迁移前备份保留。

安装后端依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

首次准备本地 PostgreSQL（要求 PostgreSQL 14 或更新版本）：

```powershell
.\scripts\setup-local-postgres.ps1
Copy-Item .env.local.example .env.local
```

日常启动数据库：

```powershell
.\scripts\start-local-postgres.ps1
```

初始化或更新数据库结构：

```powershell
cd backend
..\.venv\Scripts\python.exe manage.py migrate
```

只有全新空库需要演示数据时才执行 `manage.py seed_demo`。本地私有连接配置保存在不会提交 Git 的 `.env.local`；可提交的字段示例位于 `.env.local.example`。

启动后端：

```powershell
..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

演示账号：

```text
学员：student / Student12345
管理员：admin / Admin12345
```

JWT 登录接口：

```text
POST /api/auth/token/
POST /api/auth/token/refresh/
```

默认 access token 15 分钟过期，refresh token 7 天过期并启用轮换和拉黑。

常用 API：

```text
GET    /api/camps/current/      # 当前激活培训期、日期、投稿/投票状态与票数配置
GET    /api/tags/popular/       # 当前培训期已发布作品的热门标签及使用次数
GET    /api/search/?q=关键词
GET    /api/attendance/today/  # 学员查看本人今日签到状态，不返回签到码
POST   /api/attendance/check-in/ # 学员提交当前时段的 4 位签到码
GET    /api/attendance/admin/overview/?date=YYYY-MM-DD # 管理员查看签到码和签到数据
POST   /api/attendance/admin/generate/ # 管理员为当前时段生成唯一签到码
GET    /api/courses/             # 登录后查看当前培训期课程与资料元数据
POST   /api/courses/{id}/materials/ # 仅管理员，上传思维导图及 PDF/PPTX
GET    /api/courses/{id}/mind-map-file/ # 登录后读取受保护的思维导图
DELETE /api/courses/{id}/mind-map/ # 仅管理员删除思维导图
GET    /api/course-resources/{id}/file/ # 登录后读取受保护的课程资料
DELETE /api/course-resources/{id}/ # 仅管理员删除课程资料
POST   /api/uploads/init/       # 初始化切片上传，限制最大 500MB
POST   /api/uploads/{id}/chunk/ # 上传单个分片
POST   /api/uploads/{id}/complete/ # 合并分片，返回 upload_id
POST   /api/works/              # multipart，可传 upload_id 发布图片/PDF/视频
PATCH  /api/works/{id}/         # 作者修改作品，传 upload_id 后重新进入待审核
GET    /api/works/my/
GET    /api/works/pending/
POST   /api/works/{id}/approve/
POST   /api/works/{id}/reject/
PATCH  /api/me/                 # multipart，可上传 avatar 文件
```

签到时段为 `08:00-12:00`、`12:00-18:00`、`18:00-21:00`，均采用左闭右开区间。时间、角色、签到码、重复签到和逾期限制全部由 Django 后端校验；每个培训期每天每个时段只能生成一个签到码。签到接口默认限制为每个账号每分钟 10 次请求，同一学员在同一时段输错 5 次后会被锁定。

作品的 `tags` 字段最多接受 5 个标签，每个标签最多 20 个字符。发布和重新提交页面支持用逗号、顿号或换行分隔输入；标签会统一去除 `#`、空白并按大小写去重。热门标签完全来自当前培训期已审核发布的作品。

课程、作品、排行榜与投票额度都会按当前激活培训期隔离。培训期可在 Django 管理后台维护，同一时间只能激活一个培训期；投稿和投票起止时间留空表示不限制时间。

课程思维导图仅支持 JPG、PNG、WebP，上传成品最大 10MB、4000 万像素。管理员选择超限图片时，浏览器会在源图安全范围内自动等比例优化为 WebP；后端仍保留权威安全校验。课程资料仅支持 PDF、PPTX，单个最大 100MB、单次请求最大 200MB、每门课程最多 10 份。扩展名、图片真实格式、PDF 文件头和 PPTX 内部结构均由后端校验。课程文件不会写入公开的 `MEDIA_ROOT`，课程接口也不会返回磁盘路径。

上传会话默认 24 小时过期，完成时会校验文件真实类型并生成 SHA-256 摘要，同一个 `upload_id` 只能发布一次。建议由计划任务每小时执行一次清理：

```powershell
.\.venv\Scripts\python.exe .\backend\manage.py cleanup_uploads
```

## 批量导入学员账号

学员名单 Excel 必须包含“姓名、账号、密码”列，可选“工作单位、性别”列。密码会通过 Django 哈希后写入数据库，不会保存明文；当前“年龄”等其他列会被忽略并在执行时提示。

先在服务器执行检查，不改数据库：

```bash
python manage.py import_students /tmp/students.xlsx --dry-run
```

检查通过后正式导入：

```bash
python manage.py import_students /tmp/students.xlsx
```

默认遇到数据库中已经存在的账号会停止。如确实需要更新已有普通学员资料并重置密码，可显式增加 `--update-existing`。命令禁止覆盖管理员账号。导入完成后应立即删除服务器上的原始 Excel，名单和密码文件不得提交到 GitHub。

默认还会按照系统密码规则拦截少于 8 位、纯数字或过于常见的密码。如果组织已经发放了一次性弱初始密码，且确认需要保持原密码，可显式增加 `--allow-weak-passwords`；使用后应要求学员尽快更换密码。

管理员账号使用独立 Excel，必须包含“姓名、账号、密码、角色”列，其中角色必须为“管理员”。管理员密码始终执行强密码校验，不能使用弱密码开关：

```bash
python manage.py import_admins /tmp/admins.xlsx --dry-run
python manage.py import_admins /tmp/admins.xlsx
```

管理员导入后具有系统审核管理权限，但不会成为 Django 超级管理员。默认禁止覆盖已有账号；显式使用 `--update-existing` 可以更新普通账号或现有管理员，但超级管理员始终禁止通过批量命令修改。

## 生产环境

生产环境必须设置 `DJANGO_ENV=production` 和至少 32 位的 `DJANGO_SECRET_KEY`。系统会自动关闭 DEBUG、启用 HTTPS 跳转、安全 Cookie、HSTS 与 API 限流；缺少安全密钥时会拒绝启动。

```powershell
$env:DJANGO_ENV="production"
$env:DJANGO_SECRET_KEY="请替换为足够长的随机密钥"
$env:DJANGO_ALLOWED_HOSTS="training.example.com"
$env:DJANGO_CORS_ALLOWED_ORIGINS="https://training.example.com"
```

生产数据库可通过以下环境变量切换为 PostgreSQL：`DJANGO_DB_ENGINE=django.db.backends.postgresql`、`DJANGO_DB_NAME`、`DJANGO_DB_USER`、`DJANGO_DB_PASSWORD`、`DJANGO_DB_HOST` 和 `DJANGO_DB_PORT`。媒体文件在正式环境应由对象存储或受控的 Web 服务器提供，Django 只会在 DEBUG 模式下直接提供媒体文件。

课程资料必须配置到独立的受保护目录，并通过 Nginx `internal` 路由发送。示例环境变量：

```text
COURSE_MATERIAL_ROOT=/var/lib/new-hire-gallery/course-files
COURSE_MATERIAL_USE_X_ACCEL=true
COURSE_MATERIAL_X_ACCEL_PREFIX=/_protected_course_files/
```

Nginx 对应的 `server` 内配置：

```nginx
client_max_body_size 210m;

location /_protected_course_files/ {
    internal;
    alias /var/lib/new-hire-gallery/course-files/;
    sendfile on;
    add_header X-Content-Type-Options nosniff always;
}
```

目录应只允许 Gunicorn 服务账号读写，例如当前服务使用 `ubuntu` 时执行 `sudo install -d -o ubuntu -g ubuntu -m 750 /var/lib/new-hire-gallery/course-files`。浏览器无法直接访问该内部路由；Django 会先检查 JWT 登录状态和当前培训期，再交由 Nginx 高效传输文件。

## 并发测试

项目现提供完整 Locust 压测套件，可模拟 5 人冒烟、100 人混合使用、100 人同时上传，以及最高 200 人极限测试；同时采集服务器资源、生成性能报告，并核对点赞投票与上传文件的数据一致性。写入前会同时核验测试域名、后端压测模式、目标 ID 和当前压测培训期，任何一项不符都会停止，避免误写正式数据库。

完整安全流程和命令见 [`backend/load_tests/README.md`](backend/load_tests/README.md)。

## 本地联调顺序

先开后端：

```powershell
.\.venv\Scripts\python.exe .\backend\manage.py runserver 127.0.0.1:8001
```

再开前端：

```powershell
npm run dev -- --port 8000
```

浏览器访问：

```text
http://localhost:8000/
```
