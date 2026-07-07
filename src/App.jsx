import { useEffect, useMemo, useState } from "react";
import { api, clearTokens, getStoredTokens, login } from "./api";
import communityCover from "./assets/community-cover.png";
import galleryHero from "./assets/gallery-hero.png";

const studentTabs = [
  { id: "feed", label: "灵感", icon: "✦" },
  { id: "courses", label: "课程", icon: "◷" },
  { id: "publish", label: "发布", icon: "+" },
  { id: "profile", label: "我的", icon: "◌" },
];

const adminTabs = [
  { id: "review", label: "审核台", icon: "✓" },
  { id: "feed", label: "作品预览", icon: "✦" },
  { id: "courses", label: "课程", icon: "◷" },
];

const viewTitles = {
  feed: "发现同学们的作品",
  courses: "培训课程表",
  publish: "发布作品",
  profile: "个人主页",
  review: "内容审核台",
};

const trainingDates = [
  { value: "2026-07-18", label: "07/18", weekday: "周六" },
  { value: "2026-07-19", label: "07/19", weekday: "周日" },
  { value: "2026-07-20", label: "07/20", weekday: "周一" },
  { value: "2026-07-21", label: "07/21", weekday: "周二" },
  { value: "2026-07-22", label: "07/22", weekday: "周三" },
  { value: "2026-07-23", label: "07/23", weekday: "周四" },
  { value: "2026-07-24", label: "07/24", weekday: "周五" },
  { value: "2026-07-25", label: "07/25", weekday: "周六" },
];

const genderOptions = [
  { value: "female", label: "女" },
  { value: "male", label: "男" },
  { value: "other", label: "其他" },
  { value: "unknown", label: "未填写" },
];

const fallbackTones = ["blue", "violet", "orange"];

function App() {
  const [profile, setProfile] = useState(null);
  const [activeTab, setActiveTab] = useState("feed");
  const [booting, setBooting] = useState(true);
  const [loginError, setLoginError] = useState("");

  const role = profile?.role;
  const tabs = role === "admin" ? adminTabs : studentTabs;

  useEffect(() => {
    async function restoreSession() {
      if (!getStoredTokens().access) {
        setBooting(false);
        return;
      }

      try {
        const me = await api.me();
        setProfile(me);
        setActiveTab(me.role === "admin" ? "review" : "feed");
      } catch {
        clearTokens();
      } finally {
        setBooting(false);
      }
    }

    restoreSession();
  }, []);

  useEffect(() => {
    if (role === "admin" && !adminTabs.some((tab) => tab.id === activeTab)) {
      setActiveTab("review");
    }
    if (role === "student" && !studentTabs.some((tab) => tab.id === activeTab)) {
      setActiveTab("feed");
    }
  }, [activeTab, role]);

  async function handleLogin(username, password) {
    setLoginError("");
    await login(username, password);
    const me = await api.me();
    setProfile(me);
    setActiveTab(me.role === "admin" ? "review" : "feed");
  }

  function logout() {
    clearTokens();
    setProfile(null);
    setActiveTab("feed");
  }

  if (booting) {
    return (
      <main className="loginPage">
        <div className="loadingCard">正在恢复登录状态...</div>
      </main>
    );
  }

  if (!profile) {
    return <LoginScreen error={loginError} onError={setLoginError} onLogin={handleLogin} />;
  }

  return (
    <div className={`app ${role === "admin" ? "adminMode" : ""}`}>
      <aside className="sideNav">
        <button className="brandButton" onClick={logout} type="button" aria-label="退出登录">
          <span>新</span>
        </button>
        <nav>
          {tabs.map((tab) => (
            <button
              className={activeTab === tab.id ? "active" : ""}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              type="button"
            >
              <span>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="content">
        {!(role === "student" && activeTab === "feed") && (
          <TopBar activeTab={activeTab} role={role} onLogout={logout} />
        )}
        {activeTab === "feed" && <FeedView role={role} />}
        {activeTab === "courses" && <CourseView />}
        {activeTab === "publish" && <PublishView />}
        {activeTab === "profile" && <ProfileView profile={profile} onProfileSaved={setProfile} />}
        {activeTab === "review" && role === "admin" && <ReviewView />}
      </main>

      {role === "student" ? <StudentRail /> : <AdminRail />}
    </div>
  );
}

function LoginScreen({ error, onError, onLogin }) {
  const [username, setUsername] = useState("student");
  const [password, setPassword] = useState("Student12345");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    onError("");
    try {
      await onLogin(username.trim(), password);
    } catch (loginError) {
      onError(loginError.message || "登录失败，请检查账号密码");
    } finally {
      setSubmitting(false);
    }
  }

  function fillDemo(nextUsername, nextPassword) {
    setUsername(nextUsername);
    setPassword(nextPassword);
    onError("");
  }

  return (
    <main className="loginPage">
      <section className="loginHero">
        <div className="loginCopy">
          <span>New Hire Gallery</span>
          <h1>新人灵感墙</h1>
          <p>现在已经接入 Django 后端，登录后会用限时 Token 访问课程、作品、个人资料和审核接口。</p>
          <form className="loginForm" onSubmit={submit}>
            <label>
              账号
              <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="请输入用户名" />
            </label>
            <label>
              密码
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="请输入密码"
                type="password"
              />
            </label>
            {error && <p className="errorText">{error}</p>}
            <button disabled={submitting} type="submit">
              {submitting ? "登录中..." : "登录系统"}
            </button>
          </form>
          <div className="demoAccounts">
            <button onClick={() => fillDemo("student", "Student12345")} type="button">
              学员演示
            </button>
            <button onClick={() => fillDemo("admin", "Admin12345")} type="button">
              管理员演示
            </button>
          </div>
        </div>
        <div className="loginVisual">
          <img src={galleryHero} alt="新人展示墙视觉预览" />
          <div className="floatingNote">
            <strong>真实接口已接入</strong>
            <span>JWT 登录 · 作品审核 · 点赞投票 · 个人资料</span>
          </div>
        </div>
      </section>
    </main>
  );
}

function TopBar({ activeTab, role, onLogout }) {
  return (
    <header className="topBar">
      <div>
        <span>{role === "admin" ? "Reviewer Workspace" : "Community Feed"}</span>
        <h1>{viewTitles[activeTab]}</h1>
      </div>
      <button className="quietButton" onClick={onLogout} type="button">
        退出登录
      </button>
    </header>
  );
}

function FeedView({ role }) {
  const [selectedDate, setSelectedDate] = useState("2026-07-20");
  const [filter, setFilter] = useState("all");
  const [works, setWorks] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadFeed() {
    setLoading(true);
    setError("");
    try {
      const [nextWorks, nextLeaderboard, nextCourses] = await Promise.all([
        api.works(filter),
        api.leaderboard(),
        api.courses(selectedDate),
      ]);
      setWorks(nextWorks);
      setLeaderboard(nextLeaderboard);
      setCourses(nextCourses);
    } catch (feedError) {
      setError(feedError.message || "作品流加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFeed();
  }, [filter, selectedDate]);

  const rankedWorks = leaderboard.length
    ? leaderboard
    : [...works].sort((a, b) => scoreWork(b) - scoreWork(a)).slice(0, 5);
  const totalVotes = rankedWorks.reduce((sum, work) => sum + (work.vote_count ?? 0), 0);

  async function likeWork(id) {
    await api.likeWork(id);
    await loadFeed();
  }

  async function voteWork(id) {
    await api.voteWork(id);
    await loadFeed();
  }

  return (
    <section className="marketHome">
      <div className="marketTop">
        <button type="button">📍 新员工培训营</button>
        <button type="button">搜索作品 / 同学</button>
        <button type="button">{role === "admin" ? "管理" : "···"}</button>
      </div>

      <div className="schedulePanel">
        <div className="scheduleHead">
          <div>
            <span>课程表</span>
            <h2>7月18日 - 25日</h2>
          </div>
          <p>切换日期查看当天课程安排</p>
        </div>
        <div className="dateTabs" aria-label="课程日期">
          {trainingDates.map((day) => (
            <button
              className={selectedDate === day.value ? "active" : ""}
              key={day.value}
              onClick={() => setSelectedDate(day.value)}
              type="button"
            >
              <strong>{day.label}</strong>
              <span>{day.weekday}</span>
            </button>
          ))}
        </div>
        <div className="scheduleTable" role="table" aria-label={`${formatDate(selectedDate)} 课程表`}>
          <div className="scheduleRow scheduleHeader" role="row">
            <span>时间</span>
            <span>课程</span>
            <span>讲师 / 地点</span>
            <span>状态</span>
          </div>
          {courses.length === 0 ? (
            <div className="scheduleRow emptySchedule" role="row">
              <span>{formatDate(selectedDate)}</span>
              <strong>当天暂无课程</strong>
              <span>可以切换其他日期查看安排</span>
              <em>空</em>
            </div>
          ) : (
            courses.map((course) => (
              <div className="scheduleRow" key={course.id} role="row">
                <span>{formatCourseTime(course)}</span>
                <strong>{course.title}</strong>
                <span>{course.teacher} · {course.room}</span>
                <em className={course.status}>{course.status_label}</em>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="rankingPanel">
        <div>
          <span>🔥 点赞 / 投票排行榜</span>
          <h2>本期 TOP 5</h2>
        </div>
        <div className="rankList">
          {rankedWorks.map((work, index) => (
            <article className="rankItem" key={work.id}>
              <strong>{index + 1}</strong>
              <div>
                <h3>{work.title}</h3>
                <p>{work.author_name} · {workTypeLabel(work)}</p>
              </div>
              <span>{work.like_count ?? 0}赞 / {work.vote_count ?? 0}票</span>
            </article>
          ))}
        </div>
        <div className="feedStats">
          <strong>{totalVotes}</strong>
          <span>累计投票</span>
        </div>
      </div>

      <div className="filterRow">
        <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")} type="button">
          推荐
        </button>
        <button className={filter === "training" ? "active" : ""} onClick={() => setFilter("training")} type="button">
          培训作品
        </button>
        <button className={filter === "ai" ? "active" : ""} onClick={() => setFilter("ai")} type="button">
          AI 作品
        </button>
        {role === "admin" && <button type="button">审核视角</button>}
      </div>

      {error && <p className="errorText">{error}</p>}
      {loading ? (
        <div className="loadingCard">正在加载作品...</div>
      ) : works.length === 0 ? (
        <EmptyState title="还没有已发布作品" text="提交作品并通过审核后，会出现在这里。" />
      ) : (
        <div className="masonry">
          {works.map((work, index) => (
            <WorkCard
              index={index}
              key={work.id}
              onLike={() => likeWork(work.id)}
              onVote={() => voteWork(work.id)}
              work={work}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function WorkCard({ work, index, onLike, onVote }) {
  const image = work.image || work.image_url;
  const tone = fallbackTones[index % fallbackTones.length];

  return (
    <article className={`workCard card${index}`}>
      {image ? (
        <img className="workImage" src={image} alt={work.title} />
      ) : (
        <div className={`workImage generated ${tone}`}>
          <span>{workTypeLabel(work)}</span>
          <strong>{work.title}</strong>
        </div>
      )}
      <div className="workBody">
        <div className="tagLine">
          <span>{workTypeLabel(work)}</span>
          <span>{work.vote_count ?? 0} 票</span>
        </div>
        <h3>{work.title}</h3>
        <p>{work.description}</p>
        <div className="authorLine">
          <span className="avatar">{(work.author_name || "新").slice(0, 1)}</span>
          <strong>{work.author_name || "新员工"}</strong>
          <small>{work.status_label || "已发布"}</small>
        </div>
        {work.link && (
          <a className="workLink" href={work.link} rel="noreferrer" target="_blank">
            查看作品链接
          </a>
        )}
        <div className="actionRow">
          <button onClick={onLike} type="button">喜欢 {work.like_count ?? 0}</button>
          <button onClick={onVote} type="button">投票</button>
        </div>
      </div>
    </article>
  );
}

function CourseView() {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadCourses() {
      try {
        setCourses(await api.courses());
      } catch (courseError) {
        setError(courseError.message || "课程加载失败");
      } finally {
        setLoading(false);
      }
    }

    loadCourses();
  }, []);

  return (
    <section className="sectionPanel">
      <div className="panelTitle">
        <span>课程表</span>
        <h2>这周的培训节奏</h2>
      </div>
      {error && <p className="errorText">{error}</p>}
      {loading ? (
        <div className="loadingCard">正在加载课程...</div>
      ) : (
        <div className="courseGrid">
          {courses.map((course) => (
            <article className={`courseCard ${course.status}`} key={course.id}>
              <span>{course.status_label}</span>
              <h3>{course.title}</h3>
              <p>{course.teacher} · {course.room}</p>
              <strong>{formatDate(course.date)} {formatCourseTime(course)}</strong>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function PublishView() {
  const initialForm = { title: "", work_type: "ai", link: "", image_url: "", description: "" };
  const [form, setForm] = useState(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    setError("");

    try {
      await api.createWork(form);
      setForm(initialForm);
      setMessage("作品已提交审核，通过后会进入展示墙。");
    } catch (publishError) {
      setError(publishError.message || "提交失败，请检查内容");
    } finally {
      setSubmitting(false);
    }
  }

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  return (
    <section className="creatorScene">
      <div className="panelTitle">
        <span>发布</span>
        <h2>提交一份新人作品</h2>
        <p>提交后会进入 Django 审核流，管理员通过后才会正式出现在作品流里。</p>
      </div>
      <form className="publishForm" onSubmit={submit}>
        <label>
          作品标题
          <input
            onChange={(event) => updateField("title", event.target.value)}
            placeholder="例如：AI 入职欢迎海报"
            required
            value={form.title}
          />
        </label>
        <label>
          作品类型
          <select value={form.work_type} onChange={(event) => updateField("work_type", event.target.value)}>
            <option value="training">培训作品</option>
            <option value="ai">AI 作品</option>
          </select>
        </label>
        <label>
          作品链接
          <input
            onChange={(event) => updateField("link", event.target.value)}
            placeholder="https://..."
            type="url"
            value={form.link}
          />
        </label>
        <label>
          图片链接
          <input
            onChange={(event) => updateField("image_url", event.target.value)}
            placeholder="https://...（可选）"
            type="url"
            value={form.image_url}
          />
        </label>
        <label>
          作品介绍
          <textarea
            onChange={(event) => updateField("description", event.target.value)}
            placeholder="介绍作品背景、亮点和创作过程"
            required
            rows="5"
            value={form.description}
          />
        </label>
        {error && <p className="errorText">{error}</p>}
        {message && <p className="successText">{message}</p>}
        <button disabled={submitting} type="submit">
          {submitting ? "提交中..." : "提交审核"}
        </button>
      </form>
    </section>
  );
}

function ReviewView() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadPending() {
    setLoading(true);
    setError("");
    try {
      setItems(await api.pendingWorks());
    } catch (reviewError) {
      setError(reviewError.message || "审核队列加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPending();
  }, []);

  async function approve(id) {
    await api.approveWork(id);
    await loadPending();
  }

  async function reject(id) {
    const reason = window.prompt("请填写打回原因");
    if (!reason?.trim()) {
      return;
    }
    await api.rejectWork(id, reason.trim());
    await loadPending();
  }

  return (
    <section className="sectionPanel">
      <div className="panelTitle">
        <span>仅管理员可见</span>
        <h2>待审核内容</h2>
      </div>
      {error && <p className="errorText">{error}</p>}
      {loading ? (
        <div className="loadingCard">正在加载审核队列...</div>
      ) : items.length === 0 ? (
        <EmptyState title="审核队列已清空" text="新的作品提交后会出现在这里。" />
      ) : (
        <div className="reviewList">
          {items.map((item) => (
            <article className="reviewCard" key={item.id}>
              <div>
                <span>{workTypeLabel(item)}</span>
                <h3>{item.title}</h3>
                <p>{item.author_name} 提交 · {item.description}</p>
                {item.link && (
                  <a className="workLink" href={item.link} rel="noreferrer" target="_blank">
                    打开作品链接
                  </a>
                )}
              </div>
              <div className="reviewActions">
                <button onClick={() => approve(item.id)} type="button">通过</button>
                <button onClick={() => reject(item.id)} type="button">打回</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ProfileView({ profile, onProfileSaved }) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(profile);
  const [myWorks, setMyWorks] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(profile);
  }, [profile]);

  useEffect(() => {
    async function loadMyWorks() {
      try {
        setMyWorks(await api.myWorks());
      } catch {
        setMyWorks([]);
      }
    }

    loadMyWorks();
  }, []);

  function startEditing() {
    setDraft(profile);
    setMessage("");
    setError("");
    setIsEditing(true);
  }

  async function saveProfile(event) {
    event.preventDefault();
    setMessage("");
    setError("");

    try {
      const saved = await api.updateMe({
        name: draft.name,
        school: draft.school,
        gender: draft.gender,
        zodiac: draft.zodiac,
        mbti: draft.mbti,
        bio: draft.bio,
      });
      onProfileSaved(saved);
      setIsEditing(false);
      setMessage("个人资料已保存。");
    } catch (profileError) {
      setError(profileError.message || "资料保存失败");
    }
  }

  const heat = myWorks.reduce((sum, work) => sum + scoreWork(work), 0);
  const votes = myWorks.reduce((sum, work) => sum + (work.vote_count ?? 0), 0);

  return (
    <section className="profileScene">
      <div className="profileCover">
        <img src={galleryHero} alt="个人主页封面" />
      </div>

      <div className="profileHome">
        <div className="profileAvatarBlock">
          {profile.avatar ? (
            <img className="bigAvatar profileAvatarImage" src={profile.avatar} alt={profile.name} />
          ) : (
            <span className="bigAvatar">{profile.name?.slice(0, 1) || "新"}</span>
          )}
          <button onClick={startEditing} type="button">
            编辑资料
          </button>
        </div>

        <div className="profileMainInfo">
          <span>个人主页</span>
          <h2>{profile.name || profile.username}</h2>
          <p>{profile.bio || "这个人正在认真准备自己的展示墙。"}</p>
          <div className="profileMeta">
            <span>毕业院校：{profile.school || "未填写"}</span>
            <span>性别：{genderLabel(profile.gender)}</span>
            <span>星座：{profile.zodiac || "未填写"}</span>
            <span>MBTI：{profile.mbti || "未填写"}</span>
          </div>
          <div className="profileStats">
            <strong>
              {myWorks.length}
              <span>作品</span>
            </strong>
            <strong>
              {heat}
              <span>热度</span>
            </strong>
            <strong>
              {votes}
              <span>获票</span>
            </strong>
          </div>
          {message && <p className="successText">{message}</p>}
        </div>
      </div>

      {isEditing && (
        <form className="profileEditPanel" onSubmit={saveProfile}>
          <div className="panelTitle">
            <span>编辑资料</span>
            <h2>更新个人信息</h2>
          </div>
          <div className="profileGrid">
            <label>
              名字
              <input value={draft.name || ""} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label>
              毕业院校
              <input value={draft.school || ""} onChange={(event) => setDraft({ ...draft, school: event.target.value })} />
            </label>
            <label>
              性别
              <select value={draft.gender || "unknown"} onChange={(event) => setDraft({ ...draft, gender: event.target.value })}>
                {genderOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              星座
              <input value={draft.zodiac || ""} onChange={(event) => setDraft({ ...draft, zodiac: event.target.value })} />
            </label>
            <label>
              MBTI
              <input
                maxLength="4"
                value={draft.mbti || ""}
                onChange={(event) => setDraft({ ...draft, mbti: event.target.value.toUpperCase() })}
              />
            </label>
            <label>
              个人简介
              <textarea value={draft.bio || ""} rows="4" onChange={(event) => setDraft({ ...draft, bio: event.target.value })} />
            </label>
          </div>
          {error && <p className="errorText">{error}</p>}
          <div className="editActions">
            <button type="submit">保存资料</button>
            <button onClick={() => setIsEditing(false)} type="button">
              取消
            </button>
          </div>
        </form>
      )}

      <div className="profileWorks">
        <div className="profileWorksTitle">
          <div>
            <span>作品</span>
            <h3>我的展示墙</h3>
          </div>
          <button type="button">全部状态</button>
        </div>
        {myWorks.length === 0 ? (
          <EmptyState title="还没有作品" text="发布第一份作品后，这里会变成你的个人作品页。" />
        ) : (
          <div className="profileWorkGrid">
            {myWorks.map((work, index) => (
              <article className="profileWorkCard" key={work.id}>
                {work.image || work.image_url ? (
                  <img src={work.image || work.image_url} alt={work.title} />
                ) : (
                  <div className={`profileWorkPoster ${fallbackTones[index % fallbackTones.length]}`}>
                    <span>{workTypeLabel(work)}</span>
                  </div>
                )}
                <h4>{work.title}</h4>
                <p>{work.like_count ?? 0} 喜欢 · {work.vote_count ?? 0} 票</p>
                <strong>{work.status_label}</strong>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function StudentRail() {
  const [featured, setFeatured] = useState(null);

  useEffect(() => {
    async function loadFeatured() {
      const list = await api.leaderboard();
      setFeatured(list[0] ?? null);
    }

    loadFeatured().catch(() => setFeatured(null));
  }, []);

  return (
    <aside className="rightRail">
      <section className="featureCard">
        <img src={communityCover} alt="精选作品封面" />
        <div>
          <span>本周精选</span>
          <h2>{featured?.title || "等待第一份精选作品"}</h2>
          <p>{featured ? `${featured.like_count ?? 0} 喜欢 · ${featured.vote_count ?? 0} 票` : "榜单会自动从后端生成"}</p>
        </div>
      </section>
      <section className="topicCard">
        <h2>热门标签</h2>
        <div>
          <span>AI 海报</span>
          <span>流程 Demo</span>
          <span>知识地图</span>
          <span>结业路演</span>
        </div>
      </section>
    </aside>
  );
}

function AdminRail() {
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    async function loadPendingCount() {
      const list = await api.pendingWorks();
      setPendingCount(list.length);
    }

    loadPendingCount().catch(() => setPendingCount(0));
  }, []);

  return (
    <aside className="rightRail">
      <section className="adminSummary">
        <span>待处理</span>
        <strong>{pendingCount}</strong>
        <p>作品正在等待审核</p>
      </section>
      <section className="topicCard">
        <h2>审核规则</h2>
        <p>确认作品链接可访问、图片无敏感信息、介绍内容完整后再通过。</p>
      </section>
    </aside>
  );
}

function EmptyState({ title, text }) {
  return (
    <div className="emptyState">
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function formatDate(date) {
  if (!date) {
    return "";
  }
  return date.slice(5).replace("-", "/");
}

function formatTime(time) {
  return time?.slice(0, 5) ?? "";
}

function formatCourseTime(course) {
  return `${formatTime(course.start_time)}-${formatTime(course.end_time)}`;
}

function workTypeLabel(work) {
  return work.work_type_label || (work.work_type === "ai" ? "AI 作品" : "培训作品");
}

function genderLabel(value) {
  return genderOptions.find((option) => option.value === value)?.label ?? "未填写";
}

function scoreWork(work) {
  return (work.like_count ?? 0) + (work.vote_count ?? 0);
}

export default App;
