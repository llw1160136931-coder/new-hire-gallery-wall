import { useEffect, useMemo, useState } from "react";
import { api, clearTokens, getStoredTokens, login } from "./api";
import mascotFireReady from "./assets/mascot-fire-ready.png";
import mascotFireShare from "./assets/mascot-fire-share.png";
import mascotFireSkill from "./assets/mascot-fire-skill.png";
import mascotFireWave from "./assets/mascot-fire-wave.png";
import mascotUiLike from "./assets/mascot-ui-like-cut.png";
import mascotUiMain from "./assets/mascot-ui-main-cut.png";
import mascotUiSearch from "./assets/mascot-ui-search-cut.png";
import mascotUiSuccess from "./assets/mascot-ui-success-cut.png";
import mascotUiUpload from "./assets/mascot-ui-upload-cut.png";

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
  { value: "2026-07-19", label: "07/19", weekday: "周日" },
  { value: "2026-07-20", label: "07/20", weekday: "周一" },
  { value: "2026-07-21", label: "07/21", weekday: "周二" },
  { value: "2026-07-22", label: "07/22", weekday: "周三" },
  { value: "2026-07-23", label: "07/23", weekday: "周四" },
  { value: "2026-07-24", label: "07/24", weekday: "周五" },
];

const genderOptions = [
  { value: "female", label: "女" },
  { value: "male", label: "男" },
  { value: "other", label: "其他" },
  { value: "unknown", label: "未填写" },
];

const fallbackTones = ["blue", "violet", "orange"];
const MAX_WORK_UPLOAD_BYTES = 500 * 1024 * 1024;
const CHUNK_SIZE = 5 * 1024 * 1024;
const WORK_FILE_ACCEPT = "image/*,.pdf,application/pdf,video/mp4,video/webm,video/quicktime";
const WELCOME_SEEN_KEY = "newHireGallery.welcomeSeen";
const mascotImages = {
  ready: mascotFireReady,
  share: mascotFireShare,
  spark: mascotFireSkill,
  wave: mascotFireWave,
};

const welcomeSteps = [
  {
    eyebrow: "第 1 站 / 初来乍到",
    title: "你好，我是小火花",
    text: "从今天开始，我会陪你把培训里的灵感、练习和作品，一点点养成自己的成长档案。",
    speech: "先别急着证明自己，我们先把第一簇灵感点亮。",
    metric: "HELLO",
    mood: "wave",
    tags: ["认识同学", "查看课表", "找到方向"],
  },
  {
    eyebrow: "第 2 站 / 开始练习",
    title: "把不会，变成会一点",
    text: "课程表会告诉你今天该往哪里走；作品草稿会记录你每一次试错。别怕粗糙，成长一开始都带着铅笔痕。",
    speech: "今天学到的一点点，明天就会变成你的工具箱。",
    metric: "SKILL",
    mood: "spark",
    tags: ["AI 创作", "流程拆解", "导师反馈"],
  },
  {
    eyebrow: "第 3 站 / 分享作品",
    title: "让想法被看见",
    text: "你可以上传图片、PDF、视频，也可以留下作品链接。通过审核后，同学们会看到你的作品、为你点赞、给你投票。",
    speech: "分享不是炫耀，是把自己的路标留给后来的人。",
    metric: "SHARE",
    mood: "share",
    tags: ["发布作品", "审核通过", "点赞投票"],
  },
  {
    eyebrow: "第 4 站 / 一起长大",
    title: "你不是一个人在升级",
    text: "看别人的作品，给出喜欢和投票；收到打回也可以修改再提交。这里不是终点，是大家一起成长的展示墙。",
    speech: "准备好了吗？我们去看看今天的新灵感。",
    metric: "GO",
    mood: "ready",
    tags: ["互相看见", "继续修改", "共同成长"],
  },
];

function App() {
  const [profile, setProfile] = useState(null);
  const [activeTab, setActiveTab] = useState("feed");
  const [booting, setBooting] = useState(true);
  const [loginError, setLoginError] = useState("");
  const [showWelcome, setShowWelcome] = useState(false);

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
        setShowWelcome(shouldShowWelcome(me));
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
    setShowWelcome(shouldShowWelcome(me));
  }

  function logout() {
    clearTokens();
    setProfile(null);
    setActiveTab("feed");
    setShowWelcome(false);
  }

  function finishWelcome() {
    if (profile?.username) {
      localStorage.setItem(`${WELCOME_SEEN_KEY}.${profile.username}`, "true");
    }
    setShowWelcome(false);
  }

  function replayWelcome() {
    if (profile?.username) {
      localStorage.removeItem(`${WELCOME_SEEN_KEY}.${profile.username}`);
    }
    setShowWelcome(true);
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
          <span>火</span>
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
        {!(role === "student" && (activeTab === "feed" || activeTab === "profile")) && (
          <TopBar activeTab={activeTab} role={role} onLogout={logout} />
        )}
        {activeTab === "feed" && <FeedView role={role} />}
        {activeTab === "courses" && <CourseView />}
        {activeTab === "publish" && <PublishView />}
        {activeTab === "profile" && (
          <ProfileView profile={profile} onLogout={logout} onProfileSaved={setProfile} onReplayWelcome={replayWelcome} />
        )}
        {activeTab === "review" && role === "admin" && <ReviewView />}
      </main>

      {role === "student" ? <StudentRail /> : <AdminRail />}
      {role === "student" && showWelcome && <WelcomeCeremony profile={profile} onFinish={finishWelcome} />}
    </div>
  );
}

function shouldShowWelcome(profile) {
  return profile?.role === "student" && localStorage.getItem(`${WELCOME_SEEN_KEY}.${profile.username}`) !== "true";
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
          <div className="loginBrand">
            <img src={mascotUiMain} alt="" />
            <div>
              <span>New Hire Gallery</span>
              <h1>新人灵感墙</h1>
            </div>
          </div>
          <p>让成长被看见，让优秀被分享。登录后用限时 Token 访问课程、作品、互动、个人资料和审核流程。</p>
          <div className="loginValueGrid">
            <strong>展示自我</strong>
            <strong>互动鼓励</strong>
            <strong>成长陪伴</strong>
          </div>
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
          <div className="loginMascotPoster">
            <span>小燃陪你每一步</span>
            <img src={mascotUiMain} alt="小燃欢迎新员工" />
            <div className="posterOrbit">
              <strong>发布作品</strong>
              <strong>点赞投票</strong>
              <strong>审核通过</strong>
            </div>
          </div>
          <div className="floatingNote">
            <strong>开启成长旅程</strong>
            <span>课程 · 作品 · 互动 · 审核 · 个人主页</span>
          </div>
        </div>
      </section>
    </main>
  );
}

function WelcomeCeremony({ profile, onFinish }) {
  const [step, setStep] = useState(0);
  const [touchStart, setTouchStart] = useState(null);
  const current = welcomeSteps[step];

  function move(nextStep) {
    setStep(Math.max(0, Math.min(welcomeSteps.length - 1, nextStep)));
  }

  function handleWheel(event) {
    if (Math.abs(event.deltaY) < 18) {
      return;
    }
    move(step + (event.deltaY > 0 ? 1 : -1));
  }

  function handleTouchStart(event) {
    setTouchStart(event.touches[0]?.clientY ?? null);
  }

  function handleTouchEnd(event) {
    if (touchStart === null) {
      return;
    }
    const endY = event.changedTouches[0]?.clientY ?? touchStart;
    const distance = touchStart - endY;
    if (Math.abs(distance) > 42) {
      move(step + (distance > 0 ? 1 : -1));
    }
    setTouchStart(null);
  }

  return (
    <section className={`welcomeCeremony scene${step}`} onTouchEnd={handleTouchEnd} onTouchStart={handleTouchStart} onWheel={handleWheel}>
      <div className="welcomeDeck">
        <div className="welcomeStage" aria-hidden="true">
          <div className="storySky">
            <span />
            <span />
            <span />
          </div>
          <div className="speechBubble" key={current.speech}>
            <p>{current.speech}</p>
          </div>
          <FireMascot mood={current.mood} />
          <div className="storyGround">
            <span className="seedDot" />
            <span className="seedDot" />
            <span className="seedDot" />
          </div>
          <div className="growthPath">
            {welcomeSteps.map((item, index) => (
              <button
                className={index === step ? "active" : ""}
                key={item.title}
                onClick={() => move(index)}
                type="button"
                aria-label={`切换到${item.title}`}
              >
                <span>{index + 1}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="welcomeCopy" key={current.title}>
          <div className="welcomeBadge">
            <span>{current.eyebrow}</span>
            <strong>{current.metric}</strong>
          </div>
          <h2>{current.title}</h2>
          <p>{current.text}</p>
          <div className="welcomeTags">
            {current.tags.map((tag) => (
              <strong key={tag}>{tag}</strong>
            ))}
          </div>
          <div className="storyProgress" aria-label="欢迎流程进度">
            {welcomeSteps.map((item, index) => (
              <span className={index <= step ? "active" : ""} key={item.title} />
            ))}
          </div>
          <div className="welcomeMeta">
            <span>{profile.name || profile.username}，上下滚动或滑动切换下一页</span>
            <div>
              <button disabled={step === 0} onClick={() => move(step - 1)} type="button">
                上一页
              </button>
              {step === welcomeSteps.length - 1 ? (
                <button onClick={onFinish} type="button">和小火花一起出发</button>
              ) : (
                <button onClick={() => move(step + 1)} type="button">继续</button>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FireMascot({ mood }) {
  return (
    <div className={`fireMascot ${mood}`} aria-hidden="true">
      <span className="fireGlow" />
      <img className="fireSprite" src={mascotImages[mood] ?? mascotFireWave} alt="" />
    </div>
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
  const [selectedDate, setSelectedDate] = useState("2026-07-19");
  const [selectedCourse, setSelectedCourse] = useState(null);
  const [filter, setFilter] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [works, setWorks] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [courses, setCourses] = useState([]);
  const [selectedWork, setSelectedWork] = useState(null);
  const [loading, setLoading] = useState(true);
  const [coursesLoading, setCoursesLoading] = useState(true);
  const [error, setError] = useState("");
  const [coursesError, setCoursesError] = useState("");
  const [scheduleEpoch, setScheduleEpoch] = useState(0);

  async function loadWorks() {
    setLoading(true);
    setError("");
    try {
      const [nextWorks, nextLeaderboard] = await Promise.all([
        api.works(filter),
        api.leaderboard(),
      ]);
      setWorks(nextWorks);
      setLeaderboard(nextLeaderboard);
    } catch (feedError) {
      setError(feedError.message || "作品流加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadCourses(date = selectedDate) {
    setCoursesLoading(true);
    setCoursesError("");
    try {
      setCourses(await api.courses(date));
    } catch (courseError) {
      setCoursesError(courseError.message || "课程加载失败");
    } finally {
      setCoursesLoading(false);
    }
  }

  useEffect(() => {
    loadWorks();
  }, [filter]);

  useEffect(() => {
    loadCourses(selectedDate);
  }, [selectedDate]);

  useEffect(() => {
    if (!coursesLoading) {
      setScheduleEpoch((epoch) => epoch + 1);
    }
  }, [coursesLoading, courses]);

  const rankedWorks = leaderboard.length
    ? leaderboard
    : [...works].sort((a, b) => scoreWork(b) - scoreWork(a)).slice(0, 5);
  const totalVotes = rankedWorks.reduce((sum, work) => sum + (work.vote_count ?? 0), 0);

  async function likeWork(id) {
    await api.likeWork(id);
    await loadWorks();
  }

  async function voteWork(id) {
    await api.voteWork(id);
    await loadWorks();
  }

  async function submitSearch(event) {
    event.preventDefault();
    const nextKeyword = keyword.trim();
    if (!nextKeyword) {
      setSearchResults(null);
      return;
    }

    setSearching(true);
    setError("");
    try {
      setSearchResults(await api.search(nextKeyword));
    } catch (searchError) {
      setError(searchError.message || "搜索失败");
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setKeyword("");
    setSearchResults(null);
  }

  async function likeSelectedWork() {
    if (!selectedWork) {
      return;
    }
    await likeWork(selectedWork.id);
    setSelectedWork((current) => (current ? { ...current, like_count: (current.like_count ?? 0) + 1 } : current));
  }

  async function voteSelectedWork() {
    if (!selectedWork) {
      return;
    }
    await voteWork(selectedWork.id);
    setSelectedWork((current) => (current ? { ...current, vote_count: (current.vote_count ?? 0) + 1 } : current));
  }

  if (selectedWork) {
    return (
      <WorkDetailPage
        onBack={() => setSelectedWork(null)}
        onLike={likeSelectedWork}
        onVote={voteSelectedWork}
        work={selectedWork}
      />
    );
  }

  return (
    <section className="marketHome">
      <div className="marketTop">
        <form className="searchBox" onSubmit={submitSearch}>
          <input
            aria-label="搜索作品或同学"
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索作品 / 同学"
            value={keyword}
          />
          <button disabled={searching} type="submit">{searching ? "搜索中" : "搜索"}</button>
        </form>
        <button type="button">{role === "admin" ? "管理" : "···"}</button>
      </div>

      {searchResults && (
        <SearchResultsPanel
          keyword={keyword}
          onClear={clearSearch}
          onLike={likeWork}
          onOpenWork={setSelectedWork}
          onVote={voteWork}
          results={searchResults}
        />
      )}

      <div className="feedHero">
        <div>
          <span>新员工训练营</span>
          <h2>优秀作品展示中</h2>
          <p>分享成长，收获认可。浏览课程进度、TOP 排行榜和同学们的创意作品。</p>
          <div className="heroPills">
            <strong>课程 7/19 - 7/24</strong>
            <strong>点赞榜 TOP5</strong>
            <strong>投票榜 TOP5</strong>
          </div>
        </div>
        <img src={mascotUiMain} alt="" />
      </div>

      <div className="schedulePanel">
        <div className="scheduleHead">
          <div>
            <span>课程表</span>
            <h2>7月19日 - 24日</h2>
          </div>
          <p>切换日期查看当天课程安排</p>
        </div>
        <div className="dateTabs" aria-label="课程日期">
          {trainingDates.map((day) => (
            <button
              aria-pressed={selectedDate === day.value}
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
        {coursesError && <p className="errorText scheduleError">{coursesError}</p>}
        <div
          className={`scheduleTable ${coursesLoading ? "isUpdating" : ""}`}
          role="table"
          aria-busy={coursesLoading}
          aria-label={`${formatDate(selectedDate)} 课程表`}
        >
          <div className="scheduleRow scheduleHeader" role="row">
            <span>时间</span>
            <span>课程</span>
            <span>讲师 / 地点</span>
            <span>状态</span>
          </div>
          <div className="scheduleBody isFresh" key={scheduleEpoch}>
            {courses.length === 0 && !coursesLoading ? (
              <div className="scheduleRow emptySchedule" role="row">
                <span>{formatDate(selectedDate)}</span>
                <strong>当天暂无课程</strong>
                <span>可以切换其他日期查看安排</span>
                <em>空</em>
              </div>
            ) : (
              courses.map((course) => (
                <button className="scheduleRow scheduleActionRow" key={course.id} onClick={() => setSelectedCourse(course)} type="button" role="row">
                  <span>{formatCourseTime(course)}</span>
                  <strong>{course.title}</strong>
                  <span>{course.teacher} · {course.room}</span>
                  <em className={course.status}>{course.status_label}</em>
                </button>
              ))
            )}
          </div>
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
              onOpen={() => setSelectedWork(work)}
              onVote={() => voteWork(work.id)}
              work={work}
            />
          ))}
        </div>
      )}
      {selectedCourse && <CourseDetailModal course={selectedCourse} onClose={() => setSelectedCourse(null)} />}
    </section>
  );
}

function SearchResultsPanel({ keyword, onClear, onLike, onOpenWork, onVote, results }) {
  const workResults = results.works ?? [];
  const profileResults = results.profiles ?? [];

  return (
    <section className="searchResultsPanel">
      <div className="searchResultsHead">
        <div>
          <span>后端搜索</span>
          <h2>“{keyword.trim()}” 的结果</h2>
        </div>
        <button onClick={onClear} type="button">清除搜索</button>
      </div>

      {workResults.length === 0 && profileResults.length === 0 ? (
        <EmptyState title="没有搜到结果" text="换个作品标题、同学名字、学校或 MBTI 试试。" />
      ) : (
        <div className="searchResultGrid">
          <div>
            <h3>作品</h3>
            {workResults.length === 0 ? (
              <p className="mutedText">暂无匹配作品</p>
            ) : (
              <div className="compactWorkList">
                {workResults.map((work, index) => (
                  <WorkCard
                    index={index}
                    key={work.id}
                    onLike={() => onLike(work.id)}
                    onOpen={() => onOpenWork(work)}
                    onVote={() => onVote(work.id)}
                    work={work}
                  />
                ))}
              </div>
            )}
          </div>
          <div>
            <h3>同学</h3>
            {profileResults.length === 0 ? (
              <p className="mutedText">暂无匹配同学</p>
            ) : (
              <div className="profileSearchList">
                {profileResults.map((profile) => (
                  <article className="profileSearchCard" key={profile.username}>
                    {profile.avatar ? (
                      <img src={profile.avatar} alt={profile.name} />
                    ) : (
                      <span className="avatar">{(profile.name || "新").slice(0, 1)}</span>
                    )}
                    <div>
                      <h4>{profile.name}</h4>
                      <p>{profile.school || "未填写学校"} · {profile.gender_label || "未填写"} · {profile.zodiac || "未填写星座"}</p>
                      <small>{profile.mbti || "MBTI 未填写"}</small>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function WorkCard({ work, index, onLike, onOpen, onVote }) {
  const image = getWorkImage(work);
  const attachment = work.attachment;
  const tone = fallbackTones[index % fallbackTones.length];

  return (
    <article
      className={`workCard card${index}`}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      role="button"
      tabIndex="0"
    >
      {work.media_type === "video" && attachment ? (
        <video className="workImage" controls src={attachment} />
      ) : image ? (
        <img className="workImage" src={image} alt={work.title} />
      ) : (
        <div className={`workImage generated ${tone}`}>
          <span>{mediaTypeLabel(work)}</span>
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
          <a className="workLink" href={work.link} onClick={(event) => event.stopPropagation()} rel="noreferrer" target="_blank">
            查看作品链接
          </a>
        )}
        {attachment && (
          <a className="workLink" href={attachment} onClick={(event) => event.stopPropagation()} rel="noreferrer" target="_blank">
            打开{mediaTypeLabel(work)}
          </a>
        )}
        <div className="actionRow">
          <button
            onClick={(event) => {
              event.stopPropagation();
              onLike();
            }}
            type="button"
          >
            喜欢 {work.like_count ?? 0}
          </button>
          <button
            onClick={(event) => {
              event.stopPropagation();
              onVote();
            }}
            type="button"
          >
            投票
          </button>
        </div>
      </div>
    </article>
  );
}

function WorkDetailPage({ work, onBack, onLike, onVote }) {
  const image = getWorkImage(work);
  const attachment = work.attachment;

  return (
    <section className="workDetailPage">
      <div className="workDetailTop">
        <button onClick={onBack} type="button">‹ 返回</button>
        <span>作品详情</span>
      </div>
      <article className="workDetailCard">
        <div className="workDetailMedia">
          {work.media_type === "video" && attachment ? (
            <video controls src={attachment} />
          ) : image ? (
            <img src={image} alt={work.title} />
          ) : (
            <div className={`workDetailGenerated ${fallbackTones[work.id % fallbackTones.length]}`}>
              <span>{mediaTypeLabel(work)}</span>
              <strong>{work.title}</strong>
            </div>
          )}
        </div>
        <div className="workDetailBody">
          <div className="tagLine">
            <span>{workTypeLabel(work)}</span>
            <span>{mediaTypeLabel(work)}</span>
            <span>{work.vote_count ?? 0} 票</span>
          </div>
          <h2>{work.title}</h2>
          <div className="authorLine">
            <span className="avatar">{(work.author_name || "新").slice(0, 1)}</span>
            <strong>{work.author_name || "新员工"}</strong>
            <small>{work.status_label || "已发布"}</small>
          </div>
          <section>
            <h3>作品介绍</h3>
            <p>{work.description}</p>
          </section>
          <div className="workDetailLinks">
            {work.link && (
              <a href={work.link} rel="noreferrer" target="_blank">
                打开作品链接
              </a>
            )}
            {attachment && (
              <a href={attachment} rel="noreferrer" target="_blank">
                打开{mediaTypeLabel(work)}
              </a>
            )}
          </div>
          <div className="workDetailActions">
            <button onClick={onLike} type="button">喜欢 {work.like_count ?? 0}</button>
            <button onClick={onVote} type="button">投票</button>
          </div>
        </div>
      </article>
    </section>
  );
}

function CourseDetailModal({ course, onClose }) {
  return (
    <div className="courseDetailOverlay" onClick={onClose} role="presentation">
      <article className="courseDetailCard" onClick={(event) => event.stopPropagation()} role="dialog" aria-label="课程详情" aria-modal="true">
        <button className="courseDetailClose" onClick={onClose} type="button" aria-label="关闭">×</button>
        <div className="courseDetailHead">
          <span>{course.topic || "培训课程"}</span>
          <h2>{course.title}</h2>
          <em className={course.status}>{course.status_label}</em>
        </div>
        <div className="courseDetailMeta">
          <strong>
            上课时间
            <span>{formatDate(course.date)} {formatCourseTime(course)}</span>
          </strong>
          <strong>
            上课地点
            <span>{course.room || "待确认"}</span>
          </strong>
          <strong>
            授课师资
            <span>{course.teacher || "待确认"}</span>
          </strong>
        </div>
        <div className="courseDetailBody">
          <span>课程内容</span>
          <p>{course.content || "课程内容待补充。"}</p>
        </div>
      </article>
    </div>
  );
}

function CourseView() {
  const [courses, setCourses] = useState([]);
  const [selectedCourse, setSelectedCourse] = useState(null);
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
            <button className={`courseCard ${course.status}`} key={course.id} onClick={() => setSelectedCourse(course)} type="button">
              <span>{course.status_label}</span>
              <h3>{course.title}</h3>
              <p>{course.topic} · {course.teacher} · {course.room}</p>
              <strong>{formatDate(course.date)} {formatCourseTime(course)}</strong>
            </button>
          ))}
        </div>
      )}
      {selectedCourse && <CourseDetailModal course={selectedCourse} onClose={() => setSelectedCourse(null)} />}
    </section>
  );
}

function PublishView() {
  const initialForm = { title: "", work_type: "ai", link: "", image_url: "", asset: null, description: "" };
  const [form, setForm] = useState(initialForm);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    setError("");

    try {
      const uploadId = form.asset ? await uploadWorkAsset(form.asset, setUploadProgress) : null;
      await api.createWork(buildWorkFormData(form, uploadId));
      setForm(initialForm);
      setFileInputKey((current) => current + 1);
      setUploadProgress(null);
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
      <div className="creatorHero">
        <div className="panelTitle">
          <span>发布作品</span>
          <h2>提交一份新人作品</h2>
          <p>上传图片、PDF 或视频，提交后进入审核流，通过后正式出现在展示墙。</p>
        </div>
        <img src={mascotUiUpload} alt="" />
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
            placeholder="https://...（可选，和上传文件二选一即可）"
            type="url"
            value={form.image_url}
          />
        </label>
        <label>
          上传文件
          <input
            accept={WORK_FILE_ACCEPT}
            key={fileInputKey}
            onChange={(event) => updateField("asset", event.target.files?.[0] ?? null)}
            type="file"
          />
          <small>支持图片、PDF、MP4、WebM、MOV，最大 500MB，提交时自动切片上传。</small>
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
        {uploadProgress && (
          <p className="uploadProgress">正在上传：{uploadProgress.current}/{uploadProgress.total} 片，{uploadProgress.percent}%</p>
        )}
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
    <section className="sectionPanel reviewScene">
      <div className="reviewHero">
        <div className="panelTitle">
          <span>仅管理员可见</span>
          <h2>审核工作台</h2>
          <p>集中预览待审作品，确认内容质量后通过或打回。</p>
        </div>
        <img src={mascotUiSuccess} alt="" />
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

function ProfileView({ profile, onLogout, onProfileSaved, onReplayWelcome }) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(profile);
  const [avatarFile, setAvatarFile] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [myWorks, setMyWorks] = useState([]);
  const [editingWorkId, setEditingWorkId] = useState(null);
  const [workDraft, setWorkDraft] = useState(null);
  const [workFileInputKey, setWorkFileInputKey] = useState(0);
  const [workUploadProgress, setWorkUploadProgress] = useState(null);
  const [resubmitting, setResubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(profile);
  }, [profile]);

  async function loadMyWorks() {
    try {
      setMyWorks(await api.myWorks());
    } catch {
      setMyWorks([]);
    }
  }

  useEffect(() => {
    loadMyWorks();
  }, []);

  function startEditing() {
    setDraft(profile);
    setAvatarFile(null);
    setShowSettings(false);
    setMessage("");
    setError("");
    setIsEditing(true);
  }

  async function saveProfile(event) {
    event.preventDefault();
    setMessage("");
    setError("");

    try {
      const profilePayload = buildProfileFormData({
        name: draft.name,
        school: draft.school,
        gender: draft.gender,
        zodiac: draft.zodiac,
        mbti: draft.mbti,
        bio: draft.bio,
        avatar: avatarFile,
      });
      const saved = await api.updateMe(profilePayload);
      onProfileSaved(saved);
      setIsEditing(false);
      setMessage("个人资料已保存。");
    } catch (profileError) {
      setError(profileError.message || "资料保存失败");
    }
  }

  function startWorkEditing(work) {
    setEditingWorkId(work.id);
    setWorkDraft({
      title: work.title,
      work_type: work.work_type,
      link: work.link || "",
      image_url: work.image_url || "",
      asset: null,
      description: work.description,
    });
    setMessage("");
    setError("");
  }

  async function resubmitWork(event) {
    event.preventDefault();
    if (!editingWorkId || !workDraft) {
      return;
    }

    setResubmitting(true);
    setMessage("");
    setError("");
    try {
      const uploadId = workDraft.asset ? await uploadWorkAsset(workDraft.asset, setWorkUploadProgress) : null;
      await api.updateWork(editingWorkId, buildWorkFormData(workDraft, uploadId));
      await loadMyWorks();
      setEditingWorkId(null);
      setWorkDraft(null);
      setWorkFileInputKey((current) => current + 1);
      setWorkUploadProgress(null);
      setMessage("作品已重新提交审核。");
    } catch (workError) {
      setError(workError.message || "重新提交失败");
    } finally {
      setResubmitting(false);
    }
  }

  function updateWorkDraft(field, value) {
    setWorkDraft((current) => ({ ...current, [field]: value }));
  }

  const heat = myWorks.reduce((sum, work) => sum + scoreWork(work), 0);
  const votes = myWorks.reduce((sum, work) => sum + (work.vote_count ?? 0), 0);

  if (isEditing) {
    return (
      <section className="profileScene profileEditScene">
        <div className="profileEditTop">
          <button onClick={() => setIsEditing(false)} type="button" aria-label="返回">‹</button>
          <strong>编辑资料</strong>
          <span />
        </div>

        <form className="profileEditForm" onSubmit={saveProfile}>
          <label className="profileEditRow profileEditAvatarRow">
            <span>头像</span>
            <div>
              {profile.avatar ? (
                <img className="profileEditPreview" src={profile.avatar} alt={profile.name} />
              ) : (
                <i className="profileEditPreview">{profile.name?.slice(0, 1) || "新"}</i>
              )}
              <input accept="image/*" onChange={(event) => setAvatarFile(event.target.files?.[0] ?? null)} type="file" />
            </div>
          </label>

          <label className="profileEditRow">
            <span>昵称</span>
            <input value={draft.name || ""} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
          </label>
          <label className="profileEditRow">
            <span>学校</span>
            <input value={draft.school || ""} onChange={(event) => setDraft({ ...draft, school: event.target.value })} />
          </label>
          <label className="profileEditRow">
            <span>性别</span>
            <select value={draft.gender || "unknown"} onChange={(event) => setDraft({ ...draft, gender: event.target.value })}>
              {genderOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="profileEditRow">
            <span>星座</span>
            <input value={draft.zodiac || ""} onChange={(event) => setDraft({ ...draft, zodiac: event.target.value })} />
          </label>
          <label className="profileEditRow">
            <span>MBTI</span>
            <input
              maxLength="4"
              value={draft.mbti || ""}
              onChange={(event) => setDraft({ ...draft, mbti: event.target.value.toUpperCase() })}
            />
          </label>
          <label className="profileEditRow profileEditTextarea">
            <span>个人简介</span>
            <textarea
              maxLength="100"
              value={draft.bio || ""}
              rows="4"
              onChange={(event) => setDraft({ ...draft, bio: event.target.value })}
            />
            <small>{(draft.bio || "").length}/100</small>
          </label>

          {error && <p className="errorText">{error}</p>}
          <button className="profileSaveButton" type="submit">保存修改</button>
        </form>
      </section>
    );
  }

  return (
    <section className="profileScene">
      <div className="profilePhoneTop">
        <span>9:41</span>
        <strong>个人中心</strong>
        <button onClick={() => setShowSettings((current) => !current)} type="button" aria-label="设置">⚙</button>
        {showSettings && (
          <div className="profileSettingsMenu">
            <button onClick={startEditing} type="button">编辑资料</button>
            <button onClick={onLogout} type="button">退出登录</button>
          </div>
        )}
      </div>

      <div className="profileHeroCard">
        {profile.avatar ? (
          <img className="profileHeroAvatar" src={profile.avatar} alt={profile.name} />
        ) : (
          <span className="profileHeroAvatar">{profile.name?.slice(0, 1) || "新"}</span>
        )}
        <div className="profileHeroInfo">
          <h2>{profile.name || profile.username} <span>🔥</span></h2>
          <div className="profileMiniMeta">
            <span>{profile.school || "未填写学校"}</span>
            <span>{genderLabel(profile.gender)}</span>
            <span>{profile.zodiac || "未填写星座"}</span>
            <span>{profile.mbti || "MBTI"}</span>
          </div>
          <p>{profile.bio || "热爱设计与交互，喜欢用作品解决问题，期待和大家一起成长~"}</p>
          <button onClick={startEditing} type="button">
            ✎ 编辑资料
          </button>
        </div>
      </div>

      <button className="profileReplayCard" onClick={onReplayWelcome} type="button">
        <img src={mascotUiMain} alt="" />
        <div>
          <strong>重看欢迎动画</strong>
          <span>回顾加入时刻的温暖与期待</span>
        </div>
        <i>▶</i>
      </button>

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
      {message && <p className="successText profileMessage">{message}</p>}

      <div className="profileWorks">
        <div className="profileWorksTitle">
          <div>
            <span>作品</span>
            <h3>我的作品 <em>{myWorks.length}</em></h3>
          </div>
          <button type="button">全部作品 ›</button>
        </div>
        {myWorks.length === 0 ? (
          <EmptyState title="还没有作品" text="发布第一份作品后，这里会变成你的个人作品页。" />
        ) : (
          <div className="profileWorkGrid">
            {myWorks.map((work, index) => (
              <article className="profileWorkCard" key={work.id}>
                {getWorkImage(work) ? (
                  <img src={getWorkImage(work)} alt={work.title} />
                ) : (
                  <div className={`profileWorkPoster ${fallbackTones[index % fallbackTones.length]}`}>
                    <span>{mediaTypeLabel(work)}</span>
                  </div>
                )}
                <div className="profileWorkInfo">
                  <h4>{work.title}</h4>
                  <p>赞 {work.like_count ?? 0} · 票 {work.vote_count ?? 0}</p>
                  <small>更新于 {formatWorkDate(work.updated_at || work.created_at)}</small>
                </div>
                <strong className={work.status}>{work.status_label}</strong>
                {work.status === "rejected" && (
                  <div className="rejectInfo">
                    <span>打回原因：{work.reject_reason || "请补充作品信息后重新提交。"}</span>
                    <button onClick={() => startWorkEditing(work)} type="button">修改后重新提交</button>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
        {editingWorkId && workDraft && (
          <form className="resubmitPanel" onSubmit={resubmitWork}>
            <div className="panelTitle">
              <span>重新提交</span>
              <h2>修改被打回的作品</h2>
              <p>保存后作品会重新进入待审核状态，审核通过前不会出现在公共作品流里。</p>
            </div>
            <div className="profileGrid">
              <label>
                作品标题
                <input required value={workDraft.title} onChange={(event) => updateWorkDraft("title", event.target.value)} />
              </label>
              <label>
                作品类型
                <select value={workDraft.work_type} onChange={(event) => updateWorkDraft("work_type", event.target.value)}>
                  <option value="training">培训作品</option>
                  <option value="ai">AI 作品</option>
                </select>
              </label>
              <label>
                作品链接
                <input type="url" value={workDraft.link} onChange={(event) => updateWorkDraft("link", event.target.value)} />
              </label>
              <label>
                图片链接
                <input type="url" value={workDraft.image_url} onChange={(event) => updateWorkDraft("image_url", event.target.value)} />
              </label>
              <label>
                重新上传文件
                <input
                  accept={WORK_FILE_ACCEPT}
                  key={workFileInputKey}
                  onChange={(event) => updateWorkDraft("asset", event.target.files?.[0] ?? null)}
                  type="file"
                />
                <small>支持图片、PDF、MP4、WebM、MOV，最大 500MB。</small>
              </label>
              <label>
                作品介绍
                <textarea
                  required
                  rows="4"
                  value={workDraft.description}
                  onChange={(event) => updateWorkDraft("description", event.target.value)}
                />
              </label>
            </div>
            {error && <p className="errorText">{error}</p>}
            {workUploadProgress && (
              <p className="uploadProgress">
                正在上传：{workUploadProgress.current}/{workUploadProgress.total} 片，{workUploadProgress.percent}%
              </p>
            )}
            <div className="editActions">
              <button disabled={resubmitting} type="submit">{resubmitting ? "提交中..." : "重新提交审核"}</button>
              <button onClick={() => setEditingWorkId(null)} type="button">取消</button>
            </div>
          </form>
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
        <img src={mascotUiSearch} alt="小燃发现精选作品" />
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
        <img src={mascotUiSuccess} alt="" />
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

function formatWorkDate(value) {
  if (!value) {
    return "刚刚";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "刚刚";
  }
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function formatTime(time) {
  return time?.slice(0, 5) ?? "";
}

function formatCourseTime(course) {
  if (formatTime(course.start_time) === formatTime(course.end_time)) {
    return formatTime(course.start_time);
  }
  return `${formatTime(course.start_time)}-${formatTime(course.end_time)}`;
}

function workTypeLabel(work) {
  return work.work_type_label || (work.work_type === "ai" ? "AI 作品" : "培训作品");
}

function mediaTypeLabel(work) {
  return work.media_type_label || ({ image: "图片", pdf: "PDF", video: "视频", link: "链接" }[work.media_type] ?? "作品文件");
}

function getWorkImage(work) {
  if (work.media_type === "image" && work.attachment) {
    return work.attachment;
  }
  return work.image || work.image_url || "";
}

function genderLabel(value) {
  return genderOptions.find((option) => option.value === value)?.label ?? "未填写";
}

function scoreWork(work) {
  return (work.like_count ?? 0) + (work.vote_count ?? 0);
}

async function uploadWorkAsset(file, onProgress) {
  if (file.size > MAX_WORK_UPLOAD_BYTES) {
    throw new Error("文件不能超过 500MB");
  }

  const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1;
  const upload = await api.initUpload({
    file_name: file.name,
    content_type: file.type || guessContentType(file.name),
    total_size: file.size,
    total_chunks: totalChunks,
  });

  for (let index = 0; index < totalChunks; index += 1) {
    const chunk = file.slice(index * CHUNK_SIZE, Math.min(file.size, (index + 1) * CHUNK_SIZE));
    const formData = new FormData();
    formData.append("index", String(index));
    formData.append("chunk", chunk, `${file.name}.part${index}`);
    await api.uploadChunk(upload.upload_id, formData);
    onProgress?.({
      current: index + 1,
      total: totalChunks,
      percent: Math.round(((index + 1) / totalChunks) * 100),
    });
  }

  const completed = await api.completeUpload(upload.upload_id);
  return completed.upload_id;
}

function guessContentType(fileName) {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".mp4")) return "video/mp4";
  if (lower.endsWith(".webm")) return "video/webm";
  if (lower.endsWith(".mov")) return "video/quicktime";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".webp")) return "image/webp";
  return "image/jpeg";
}

function buildWorkFormData(work, uploadId = null) {
  const formData = new FormData();
  formData.append("title", work.title);
  formData.append("work_type", work.work_type);
  formData.append("link", work.link || "");
  formData.append("image_url", work.image_url || "");
  formData.append("description", work.description);
  if (uploadId) {
    formData.append("upload_id", uploadId);
  }
  return formData;
}

function buildProfileFormData(profile) {
  const formData = new FormData();
  formData.append("name", profile.name || "");
  formData.append("school", profile.school || "");
  formData.append("gender", profile.gender || "unknown");
  formData.append("zodiac", profile.zodiac || "");
  formData.append("mbti", profile.mbti || "");
  formData.append("bio", profile.bio || "");
  if (profile.avatar instanceof File) {
    formData.append("avatar", profile.avatar);
  }
  return formData;
}

export default App;
