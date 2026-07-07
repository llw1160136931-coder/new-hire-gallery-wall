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

- 学员发布培训作品或 AI 作品，支持填写图片地址和作品链接。
- 新作品默认进入待审核状态。
- 管理员可在审核中心通过或打回作品。
- 通过审核的作品展示在作品墙，支持点赞和投票。
- 首页课程表自动区分已结束、进行中、未开始。
- 个人中心支持编辑姓名、头像、毕业院校、MBTI、星座和性别。

当前版本的 React 前端已接入 Django API，登录使用限时 JWT access token，并在过期时尝试用 refresh token 自动续期。

## 后端开发

后端使用 Django + Django REST Framework，开发期默认 SQLite。

安装后端依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

初始化数据库：

```powershell
cd backend
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py seed_demo
```

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
