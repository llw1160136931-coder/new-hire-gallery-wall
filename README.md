# 新员工展示墙系统

一个 Vite + React + Django REST Framework 项目，用于新员工培训作品展示、课程安排、点赞投票与管理员审核。

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
- 个人中心支持编辑姓名、头像、毕业院校、MBTI、星座和性别。

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

作品的 `tags` 字段最多接受 5 个标签，每个标签最多 20 个字符。发布和重新提交页面支持用逗号、顿号或换行分隔输入；标签会统一去除 `#`、空白并按大小写去重。热门标签完全来自当前培训期已审核发布的作品。

课程、作品、排行榜与投票额度都会按当前激活培训期隔离。培训期可在 Django 管理后台维护，同一时间只能激活一个培训期；投稿和投票起止时间留空表示不限制时间。

上传会话默认 24 小时过期，完成时会校验文件真实类型并生成 SHA-256 摘要，同一个 `upload_id` 只能发布一次。建议由计划任务每小时执行一次清理：

```powershell
.\.venv\Scripts\python.exe .\backend\manage.py cleanup_uploads
```

## 生产环境

生产环境必须设置 `DJANGO_ENV=production` 和至少 32 位的 `DJANGO_SECRET_KEY`。系统会自动关闭 DEBUG、启用 HTTPS 跳转、安全 Cookie、HSTS 与 API 限流；缺少安全密钥时会拒绝启动。

```powershell
$env:DJANGO_ENV="production"
$env:DJANGO_SECRET_KEY="请替换为足够长的随机密钥"
$env:DJANGO_ALLOWED_HOSTS="training.example.com"
$env:DJANGO_CORS_ALLOWED_ORIGINS="https://training.example.com"
```

生产数据库可通过以下环境变量切换为 PostgreSQL：`DJANGO_DB_ENGINE=django.db.backends.postgresql`、`DJANGO_DB_NAME`、`DJANGO_DB_USER`、`DJANGO_DB_PASSWORD`、`DJANGO_DB_HOST` 和 `DJANGO_DB_PORT`。媒体文件在正式环境应由对象存储或受控的 Web 服务器提供，Django 只会在 DEBUG 模式下直接提供媒体文件。

## 并发测试

`backend/load_tests/run_load_test.py` 提供 `login`、`public`、`auth-read` 和 `mixed` 四个场景，可模拟 100 个独立用户。脚本会创建和清理测试数据，因此只允许连接文件名包含 `loadtest` 的独立数据库，严禁直接连接生产数据库。

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
