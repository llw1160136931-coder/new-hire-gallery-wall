# 展示墙

React + Vite 前端项目，当前通过 Mock 数据层运行；后端接口已预留，二期对接 Express 服务即可。

## 快速开始

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

### Mock / 真实后端切换

| 环境变量 | 值 | 说明 |
|----------|-----|------|
| `VITE_USE_MOCK` | `true`（默认） | 使用 `src/api/mock.js` 等 Mock 实现 |
| `VITE_USE_MOCK` | `false` | 请求真实后端 `http://localhost:3001` |

开发代理（`vite.config.js`）：

- `/api` → `http://localhost:3001`
- `/uploads` → `http://localhost:3001`

### 前端 API 统一出口

所有页面通过 [`src/api/client.js`](src/api/client.js) 调用接口，不直接访问 Mock 模块。

---

## 数据类型

### User

```json
{
  "id": 1,
  "name": "张三",
  "avatar": "可选，头像 URL"
}
```

### Work

```json
{
  "id": 1,
  "userId": 1,
  "authorName": "张三",
  "content": "作品文字内容",
  "images": ["/uploads/xxx.jpg"],
  "status": "pending | approved | rejected",
  "likeCount": 24,
  "todayLikeCount": 8,
  "createdAt": "2026-07-07T08:00:00.000Z"
}
```

| 字段 | 说明 |
|------|------|
| `status` | `pending` 审核中；`approved` 已通过（首页可见）；`rejected` 已拒绝 |
| `todayLikeCount` | 当日点赞数，用于排行榜「今日」维度 |

### CreateWorkPayload（上传投稿）

| 字段 | 类型 | 说明 |
|------|------|------|
| `userId` | number | 当前登录用户 ID |
| `content` | string | 文字内容 |
| `images` | File[] | 多张图片文件 |

### Course

```json
{
  "id": 1,
  "title": "创意绘画入门",
  "date": "2026-07-07"
}
```

日期范围：`2026-07-01` ~ `2026-08-31`（见 `src/api/types.js` 中 `COURSE_DATE_MIN` / `COURSE_DATE_MAX`）。

### CreateCoursePayload

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | string | 课程标题 |
| `date` | string | `YYYY-MM-DD` |

### UpdateCoursePayload

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | string | 可选 |
| `date` | string | 可选 |

### RankPeriod

`today` | `total` — 排行榜按今日点赞或累计点赞排序。

---

## 接口一览

| 前端函数 | 方法 | 路径 | 说明 |
|----------|------|------|------|
| `loginUser` | POST | `/api/auth/login` | 用户登录 |
| `loginAdmin` | POST | `/api/auth/login` | 管理员登录 |
| `getApprovedWorks` | GET | `/api/works` | 首页已通过作品列表 |
| `getWorkById` | GET | `/api/works/:id` | 作品详情 |
| `getMyWorks` | GET | `/api/works/my` | 我的投稿列表 |
| `createWork` | POST | `/api/works` | 上传投稿 |
| `likeWork` | POST | `/api/works/:id/like` | 点赞 |
| `getRankedWorks` | GET | `/api/works/rank` | 排行榜 |
| `getPendingSubmissions` | GET | `/api/admin/submissions` | 待审核投稿 |
| `reviewSubmission` | PATCH | `/api/admin/submissions/:id` | 审核投稿 |
| `getCourses` | GET | `/api/courses` | 全部课程 |
| `getCoursesByDate` | GET | `/api/courses` | 按日期查课程 |
| `createCourse` | POST | `/api/courses` | 添加课程 |
| `updateCourse` | PATCH | `/api/courses/:id` | 编辑课程 |
| `deleteCourse` | DELETE | `/api/courses/:id` | 删除课程 |
| — | GET | `/uploads/:filename` | 静态图片访问 |

---

## 认证

### POST `/api/auth/login`

用户与管理员共用路径，通过 `role` 区分。

**请求体（JSON）**

```json
{
  "name": "张三",
  "role": "user"
}
```

| `role` | 说明 |
|--------|------|
| `user` | 用户登录 |
| `admin` | 管理员登录 |

**成功响应 `200`**

```json
{
  "id": 1,
  "name": "张三"
}
```

**失败响应 `404`**

```json
{
  "message": "用户不存在，请检查昵称"
}
```

Mock 预置账号：

| 类型 | 名称 |
|------|------|
| 用户 | 张三、李四 |
| 管理员 | 管理员 |

> 暂未启用密码字段；二期可扩展 `password`。

---

## 作品（Works）

### GET `/api/works`

获取首页展示的作品（仅 `status = approved`），按创建时间倒序。

**响应 `200`**：`Work[]`

---

### GET `/api/works/:id`

获取单条作品详情。

**路径参数**

| 参数 | 说明 |
|------|------|
| `id` | 作品 ID |

**响应 `200`**：`Work`

**失败 `404`**：作品不存在

---

### GET `/api/works/my`

获取指定用户的全部投稿（含 pending / approved / rejected）。

**查询参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `userId` | number | 是 | 用户 ID |

**响应 `200`**：`Work[]`

---

### POST `/api/works`

上传新投稿，初始状态为 `pending`。

**请求体（multipart/form-data）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `userId` | string | 用户 ID |
| `content` | string | 文字内容 |
| `images` | File | 可多个，字段名均为 `images` |

**响应 `201`**：`Work`

---

### POST `/api/works/:id/like`

对作品点赞。同一用户对同一作品只能点赞一次。

**路径参数**

| 参数 | 说明 |
|------|------|
| `id` | 作品 ID |

**请求体（JSON）**

```json
{
  "userId": 1
}
```

**响应 `200`**

```json
{
  "likeCount": 25
}
```

**失败 `409`**：已经点赞过了

---

### GET `/api/works/rank`

排行榜，仅包含 `approved` 作品。

**查询参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `period` | `today` \| `total` | `today` 按当日点赞；`total` 按累计点赞 |

**响应 `200`**：`Work[]`（按对应点赞数降序）

---

### 前端辅助：`hasLiked(workId, userId)`

| 项目 | 说明 |
|------|------|
| 位置 | `src/api/client.js` |
| Mock | 读取 localStorage，键为 `userId:workId` |
| 真实后端（建议） | `GET /api/works/:id/liked?userId=` 或在详情接口中返回 `liked: boolean` |

---

## 管理员（Admin）

### GET `/api/admin/submissions`

获取待审核投稿列表（`status = pending`），按创建时间倒序。

**响应 `200`**：`Work[]`

---

### PATCH `/api/admin/submissions/:id`

审核投稿。

**路径参数**

| 参数 | 说明 |
|------|------|
| `id` | 作品 ID |

**请求体（JSON）**

```json
{
  "status": "approved"
}
```

| `status` | 说明 |
|----------|------|
| `approved` | 通过，首页可见 |
| `rejected` | 拒绝 |

**响应 `200`**：`Work`（更新后的完整对象）

**失败 `404`**：投稿不存在

---

## 课程（Courses）

课程与作品相互独立。

### GET `/api/courses`

**无查询参数**：返回全部课程，按日期升序。

**查询参数 `date`**：返回指定日期的课程。

| 参数 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `date` | string | `2026-07-07` | 可选，`YYYY-MM-DD` |

**响应 `200`**：`Course[]`

---

### POST `/api/courses`

添加课程（管理员）。

**请求体（JSON）**

```json
{
  "title": "创意绘画入门",
  "date": "2026-07-07"
}
```

**响应 `201`**：`Course`

**失败 `400`**：日期不在 7 月–8 月末范围内

---

### PATCH `/api/courses/:id`

编辑课程。

**路径参数**

| 参数 | 说明 |
|------|------|
| `id` | 课程 ID |

**请求体（JSON）**（字段均可选，至少传一个）

```json
{
  "title": "新标题",
  "date": "2026-08-01"
}
```

**响应 `200`**：`Course`

**失败 `404`**：课程不存在

---

### DELETE `/api/courses/:id`

删除课程。

**路径参数**

| 参数 | 说明 |
|------|------|
| `id` | 课程 ID |

**响应 `204`**：无内容

**失败 `404`**：课程不存在

---

## 静态资源

### GET `/uploads/:filename`

上传图片的访问路径。二期后端将文件存储在 `uploads/` 目录并通过此路径提供。

---

## 通用错误格式（建议）

二期后端建议统一错误响应：

```json
{
  "message": "错误描述"
}
```

| HTTP 状态码 | 场景 |
|-------------|------|
| `400` | 参数校验失败（如课程日期越界） |
| `404` | 资源不存在（用户、作品、课程等） |
| `409` | 冲突（如重复点赞） |

---

## 项目结构

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.js       # 统一 API 出口
│   │   ├── types.js        # 类型与常量
│   │   ├── mock.js         # 作品 Mock
│   │   ├── courseMock.js   # 课程 Mock
│   │   └── userMock.js     # 用户 / 登录 Mock
│   ├── components/
│   ├── context/AuthContext.jsx
│   └── pages/
└── vite.config.js
```

## 二期后端对接清单

- [ ] 实现上述 REST 接口
- [ ] 设置 `VITE_USE_MOCK=false`
- [ ] 图片上传存储至 `uploads/` 并返回 `/uploads/...` URL
- [ ] 使用 SQLite 等持久化替代 sessionStorage / localStorage
- [ ] 可选：为 `hasLiked` 增加 `GET /api/works/:id/liked` 接口
