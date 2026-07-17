import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import {
  guessContentType,
  MAX_WORK_IMAGE_COUNT,
  MAX_WORK_UPLOAD_BYTES,
  mergeSelectedWorkFiles,
  WORK_FILE_ACCEPT,
} from "./workFileSelection";

const studentTabs = [
  { id: "feed", label: "灵感", icon: "✦" },
  { id: "works", label: "作品", icon: "▦" },
  { id: "publish", label: "发布", icon: "+" },
  { id: "courses", label: "课程", icon: "◷" },
  { id: "profile", label: "我的", icon: "◌" },
];

const adminTabs = [
  { id: "review", label: "审核台", icon: "✓" },
  { id: "attendance", label: "签到台", icon: "◎" },
  { id: "feed", label: "首页预览", icon: "✦" },
  { id: "works", label: "作品", icon: "▦" },
  { id: "courses", label: "课程", icon: "◷" },
];

const viewTitles = {
  feed: "发现同学们的作品",
  works: "全部作品",
  courses: "培训课程表",
  publish: "发布作品",
  profile: "个人主页",
  review: "内容审核台",
  attendance: "签到管理台",
};

const genderOptions = [
  { value: "female", label: "女" },
  { value: "male", label: "男" },
  { value: "other", label: "其他" },
  { value: "unknown", label: "未填写" },
];

const mbtiOptions = [
  "INTJ", "INTP", "ENTJ", "ENTP",
  "INFJ", "INFP", "ENFJ", "ENFP",
  "ISTJ", "ISFJ", "ESTJ", "ESFJ",
  "ISTP", "ISFP", "ESTP", "ESFP",
];

const zodiacOptions = [
  "白羊座", "金牛座", "双子座", "巨蟹座",
  "狮子座", "处女座", "天秤座", "天蝎座",
  "射手座", "摩羯座", "水瓶座", "双鱼座",
];

const fallbackTones = ["blue", "violet", "orange"];
const CHUNK_SIZE = 5 * 1024 * 1024;
const MAX_COURSE_RESOURCE_COUNT = 10;
const COURSE_MIND_MAP_ACCEPT = ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";
const COURSE_RESOURCE_ACCEPT = ".pdf,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation";
const WELCOME_SEEN_KEY = "newHireGallery.welcomeSeen";
const REVIEW_REJECT_TEMPLATES = [
  "作品介绍不够完整，请补充背景、亮点和创作过程。",
  "作品链接或附件暂时无法打开，请检查后重新提交。",
  "内容需要规避敏感信息，请处理后再次提交。",
  "文件预览不清晰，请上传更清楚的版本。",
];
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
    text: "你可以上传图片、PDF、HTML、视频，也可以留下作品链接。通过审核后，同学们会看到你的作品、为你点赞、给你投票。",
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
  const [camp, setCamp] = useState(null);
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
        const [me, currentCamp] = await Promise.all([api.me(), api.currentCamp().catch(() => null)]);
        setProfile(me);
        setCamp(currentCamp);
        setActiveTab(me.role === "admin" ? "review" : "feed");
        setShowWelcome(shouldShowWelcome(me, currentCamp));
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
    const [me, currentCamp] = await Promise.all([api.me(), api.currentCamp().catch(() => null)]);
    setProfile(me);
    setCamp(currentCamp);
    setActiveTab(me.role === "admin" ? "review" : "feed");
    setShowWelcome(shouldShowWelcome(me, currentCamp));
  }

  function logout() {
    clearTokens();
    setProfile(null);
    setCamp(null);
    setActiveTab("feed");
    setShowWelcome(false);
  }

  function finishWelcome() {
    if (profile?.username) {
      localStorage.setItem(welcomeStorageKey(profile, camp), "true");
    }
    setShowWelcome(false);
  }

  function replayWelcome() {
    if (profile?.username) {
      localStorage.removeItem(welcomeStorageKey(profile, camp));
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
              className={`${activeTab === tab.id ? "active " : ""}nav-${tab.id}`}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              type="button"
            >
              <span className="navIcon">{tab.icon}</span>
              <span className="navLabel">{tab.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <main className="content">
        {!(role === "student" && (activeTab === "feed" || activeTab === "works" || activeTab === "profile")) && (
          <TopBar activeTab={activeTab} role={role} onLogout={logout} />
        )}
        {activeTab === "feed" && <FeedView camp={camp} role={role} />}
        {activeTab === "works" && <WorksGalleryView role={role} />}
        {activeTab === "courses" && <CourseView camp={camp} role={role} />}
        {activeTab === "publish" && <PublishView camp={camp} />}
        {activeTab === "profile" && (
          <ProfileView profile={profile} onLogout={logout} onProfileSaved={setProfile} onReplayWelcome={replayWelcome} />
        )}
        {activeTab === "review" && role === "admin" && <ReviewView />}
        {activeTab === "attendance" && role === "admin" && <AdminAttendanceView />}
      </main>

      {role === "student" ? <StudentRail /> : <AdminRail />}
      {role === "student" && showWelcome && <WelcomeCeremony profile={profile} onFinish={finishWelcome} />}
    </div>
  );
}

function welcomeStorageKey(profile, camp) {
  return `${WELCOME_SEEN_KEY}.${camp?.slug || "default"}.${profile?.username || "unknown"}`;
}

function shouldShowWelcome(profile, camp) {
  return profile?.role === "student" && localStorage.getItem(welcomeStorageKey(profile, camp)) !== "true";
}

function LoginScreen({ error, onError, onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
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
          <p className="loginSlogan">
            <strong>让成长被看见</strong>
            <i>让优秀被分享</i>
          </p>
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
  const current = welcomeSteps[step];

  function move(nextStep) {
    setStep(Math.max(0, Math.min(welcomeSteps.length - 1, nextStep)));
  }

  return (
    <section className={`welcomeCeremony scene${step}`}>
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
            <span>{profile.name || profile.username}，请点击按钮查看下一页</span>
            <div>
              <button disabled={step === 0} onClick={() => move(step - 1)} type="button">
                上一页
              </button>
              {step === welcomeSteps.length - 1 ? (
                <button onClick={onFinish} type="button">进入系统</button>
              ) : (
                <button onClick={() => move(step + 1)} type="button">下一页</button>
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

function FeedView({ camp, role }) {
  const trainingDates = useMemo(() => buildTrainingDates(camp), [camp]);
  const [selectedDate, setSelectedDate] = useState(camp?.training_dates?.[0] || "");
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
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [scheduleEpoch, setScheduleEpoch] = useState(0);

  useEffect(() => {
    const firstDate = trainingDates[0]?.value || "";
    if (!trainingDates.some((day) => day.value === selectedDate)) {
      setSelectedDate(firstDate);
    }
  }, [selectedDate, trainingDates]);

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

  function syncWorkFromResponse(nextWork) {
    if (!nextWork) {
      return;
    }

    setWorks((current) => current.map((work) => (work.id === nextWork.id ? nextWork : work)));
    setSelectedWork((current) => (current?.id === nextWork.id ? nextWork : current));
    setSearchResults((current) => {
      if (!current?.works) {
        return current;
      }

      return {
        ...current,
        works: current.works.map((work) => (work.id === nextWork.id ? nextWork : work)),
      };
    });
  }

  useEffect(() => {
    loadWorks();
  }, [filter]);

  useEffect(() => {
    if (selectedDate) {
      loadCourses(selectedDate);
    }
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
    setActionMessage("");
    setActionError("");
    try {
      const response = await api.likeWork(id);
      syncWorkFromResponse(response?.work);
      setActionMessage(response?.detail || "点赞成功");
      await loadWorks();
      return response;
    } catch (actionFailure) {
      syncWorkFromResponse(actionFailure.details?.work);
      setActionError(actionFailure.message || "点赞失败");
      return null;
    }
  }

  async function voteWork(id) {
    setActionMessage("");
    setActionError("");
    try {
      const response = await api.voteWork(id);
      syncWorkFromResponse(response?.work);
      setActionMessage(response?.detail || "投票成功");
      await loadWorks();
      return response;
    } catch (actionFailure) {
      syncWorkFromResponse(actionFailure.details?.work);
      setActionError(actionFailure.message || "投票失败");
      return null;
    }
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
  }

  async function voteSelectedWork() {
    if (!selectedWork) {
      return;
    }
    await voteWork(selectedWork.id);
  }

  if (selectedWork) {
    return (
      <WorkDetailPage
        actionError={actionError}
        actionMessage={actionMessage}
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

      {actionError && <p className="errorText interactionNotice" role="alert">{actionError}</p>}
      {actionMessage && <p aria-live="polite" className="successText interactionNotice" role="status">{actionMessage}</p>}

      <div className="feedHero">
        <div>
          <span>新员工训练营</span>
          <h2>优秀作品展示中</h2>
          <p>分享成长，收获认可。浏览课程进度、TOP 排行榜和同学们的创意作品。</p>
          <div className="heroPills">
            <strong>课程 {formatCampRange(camp)}</strong>
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
            <h2>{formatCampRange(camp)}</h2>
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

      <div className="feedToolbar">
        <div className="filterRow" aria-label="作品类型" role="group">
          <button aria-pressed={filter === "all"} className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")} type="button">
            推荐
          </button>
          <button aria-pressed={filter === "training"} className={filter === "training" ? "active" : ""} onClick={() => setFilter("training")} type="button">
            培训作品
          </button>
          <button aria-pressed={filter === "ai"} className={filter === "ai" ? "active" : ""} onClick={() => setFilter("ai")} type="button">
            AI 作品
          </button>
        </div>
        <span className="feedWorkCount"><strong>{works.length}</strong> 个作品</span>
      </div>

      {error && <p className="errorText">{error}</p>}
      {loading ? (
        <div className="loadingCard">正在加载作品...</div>
      ) : works.length === 0 ? (
        <EmptyState title="还没有已发布作品" text="提交作品并通过审核后，会出现在这里。" />
      ) : (
        <MasonryGrid itemsKey={works.map((work) => work.id).join("|")}>
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
        </MasonryGrid>
      )}
      {selectedCourse && (
        <CourseDetailModal
          course={selectedCourse}
          onClose={() => setSelectedCourse(null)}
          onCourseChange={(nextCourse) => {
            setCourses((current) => current.map((item) => (item.id === nextCourse.id ? nextCourse : item)));
            setSelectedCourse(nextCourse);
          }}
          role={role}
        />
      )}
    </section>
  );
}

function WorksGalleryView({ role }) {
  const [works, setWorks] = useState([]);
  const [filter, setFilter] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [selectedWork, setSelectedWork] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [deletingWorkId, setDeletingWorkId] = useState(null);

  async function loadWorks() {
    setLoading(true);
    setError("");
    try {
      setWorks(await api.works(filter));
    } catch (loadError) {
      setError(loadError.message || "作品加载失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWorks();
  }, [filter]);

  const visibleWorks = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    if (!normalizedKeyword) {
      return works;
    }
    return works.filter((work) => [
      work.title,
      work.description,
      work.author_name,
      ...(work.tags || []),
    ].some((value) => String(value || "").toLowerCase().includes(normalizedKeyword)));
  }, [keyword, works]);

  function syncWork(nextWork) {
    if (!nextWork) {
      return;
    }
    setWorks((current) => current.map((work) => (work.id === nextWork.id ? nextWork : work)));
    setSelectedWork((current) => (current?.id === nextWork.id ? nextWork : current));
  }

  async function likeWork(work) {
    setActionMessage("");
    setActionError("");
    try {
      const response = await api.likeWork(work.id);
      syncWork(response?.work);
      setActionMessage(response?.detail || "点赞成功");
    } catch (actionFailure) {
      syncWork(actionFailure.details?.work);
      setActionError(actionFailure.message || "点赞失败");
    }
  }

  async function voteWork(work) {
    setActionMessage("");
    setActionError("");
    try {
      const response = await api.voteWork(work.id);
      syncWork(response?.work);
      setActionMessage(response?.detail || "投票成功");
    } catch (actionFailure) {
      syncWork(actionFailure.details?.work);
      setActionError(actionFailure.message || "投票失败");
    }
  }

  async function deleteWork(work) {
    if (!window.confirm(`确定删除“${work.title}”吗？删除后无法恢复。`)) {
      return;
    }
    setDeletingWorkId(work.id);
    setActionMessage("");
    setActionError("");
    try {
      await api.deleteWork(work.id);
      setWorks((current) => current.filter((item) => item.id !== work.id));
      setActionMessage("作品已删除。");
    } catch (deleteError) {
      setActionError(deleteError.message || "删除失败，请稍后重试");
    } finally {
      setDeletingWorkId(null);
    }
  }

  if (selectedWork) {
    return (
      <WorkDetailPage
        actionError={actionError}
        actionMessage={actionMessage}
        onBack={() => setSelectedWork(null)}
        onLike={() => likeWork(selectedWork)}
        onVote={() => voteWork(selectedWork)}
        work={selectedWork}
      />
    );
  }

  return (
    <section className="worksGalleryPage">
      <header className="worksGalleryHeader">
        <div>
          <span>COMMUNITY GALLERY</span>
          <h1>大家的作品</h1>
          <p>向下滑动，看看同学们最新发布的灵感与成果。</p>
        </div>
        <strong>{visibleWorks.length}<small> 个作品</small></strong>
      </header>

      <div className="worksGalleryToolbar">
        <div className="worksGalleryFilters" aria-label="作品分类">
          <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")} type="button">全部</button>
          <button className={filter === "training" ? "active" : ""} onClick={() => setFilter("training")} type="button">培训作品</button>
          <button className={filter === "ai" ? "active" : ""} onClick={() => setFilter("ai")} type="button">AI 作品</button>
        </div>
        <label className="worksGallerySearch">
          <span>⌕</span>
          <input aria-label="搜索作品" onChange={(event) => setKeyword(event.target.value)} placeholder="搜索标题、作者或标签" value={keyword} />
          {keyword && <button aria-label="清空搜索" onClick={() => setKeyword("")} type="button">×</button>}
        </label>
      </div>

      {actionError && <p className="errorText interactionNotice" role="alert">{actionError}</p>}
      {actionMessage && <p aria-live="polite" className="successText interactionNotice" role="status">{actionMessage}</p>}
      {error && <p className="errorText">{error}</p>}

      {loading ? (
        <div className="galleryLoadingGrid" aria-label="正在加载作品">
          {Array.from({ length: 8 }, (_, index) => <span key={index} />)}
        </div>
      ) : visibleWorks.length === 0 ? (
        <EmptyState
          title={keyword ? "没有找到相关作品" : "还没有已发布作品"}
          text={keyword ? "换一个标题、作者或标签试试。" : "作品通过审核后会显示在这里。"}
        />
      ) : (
        <div className="worksWaterfall">
          {visibleWorks.map((work, index) => (
            <GalleryWorkCard
              index={index}
              key={work.id}
              deleting={deletingWorkId === work.id}
              onLike={() => likeWork(work)}
              onOpen={() => setSelectedWork(work)}
              onDelete={role === "admin" ? () => deleteWork(work) : null}
              work={work}
            />
          ))}
        </div>
      )}
      {!loading && visibleWorks.length > 0 && <p className="galleryEnd">— 已经看到全部作品啦 —</p>}
    </section>
  );
}

function GalleryWorkCard({ work, index, deleting, onDelete, onLike, onOpen }) {
  const images = getWorkImages(work);
  const image = images[0] || getWorkImage(work);
  const isVideo = work.media_type === "video" && work.attachment;
  const tone = fallbackTones[index % fallbackTones.length];

  return (
    <article className="galleryWorkCard">
      <button className="galleryWorkCover" onClick={onOpen} type="button">
        {isVideo ? (
          <>
            <video muted playsInline preload="metadata" src={work.attachment} />
            <span className="galleryPlayIcon">▶</span>
          </>
        ) : image ? (
          <img loading="lazy" src={image} alt={work.title} />
        ) : (
          <div className={`galleryGenerated ${tone}`}>
            <span>{mediaTypeLabel(work)}</span>
            <strong>{work.title}</strong>
          </div>
        )}
        {images.length > 1 && <span className="galleryImageCount">▣ {images.length}</span>}
      </button>
      <div className="galleryWorkInfo">
        <button className="galleryWorkTitle" onClick={onOpen} type="button">
          <strong>{work.title}</strong>
        </button>
        {(work.tags || []).length > 0 && (
          <div className="galleryWorkTags">
            {(work.tags || []).slice(0, 2).map((tag) => <span key={tag}>#{tag}</span>)}
          </div>
        )}
        <div className="galleryWorkMeta">
          <button className="galleryAuthor" onClick={onOpen} type="button">
            {work.author_avatar ? (
              <img src={work.author_avatar} alt="" />
            ) : (
              <span>{(work.author_name || "新").slice(0, 1)}</span>
            )}
            <small>{work.author_name || "新员工"}</small>
          </button>
          <button className="galleryLike" onClick={onLike} type="button" aria-label={`喜欢 ${work.title}`}>
            ♡ <span>{work.like_count ?? 0}</span>
          </button>
        </div>
        {onDelete && (
          <button className="galleryDelete" disabled={deleting} onClick={onDelete} type="button">
            {deleting ? "删除中..." : "管理员删除"}
          </button>
        )}
      </div>
    </article>
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
        <EmptyState title="没有搜到结果" text="换个作品标题、同学名字、工作单位或 MBTI 试试。" />
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
                      <p>{profile.workplace || "未填写工作单位"} · {profile.gender_label || "未填写"} · {profile.zodiac || "未填写星座"}</p>
                      <small>{profile.mbti || "MBTI 未填写"} · {profile.training_group_label || "未分组"}</small>
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
  const images = getWorkImages(work);
  const image = images[0] || getWorkImage(work);
  const attachment = work.attachment;
  const tone = fallbackTones[index % fallbackTones.length];

  return (
    <article className="workCard">
      {work.media_type === "video" && attachment ? (
        <video className="workImage" controls src={attachment} />
      ) : (
        <button aria-label={`查看 ${work.title} 详情`} className="workPreviewButton" onClick={onOpen} type="button">
          {image ? (
            <div className="workImageStack">
              <img className="workImage" src={image} alt={work.title} loading="lazy" />
              {images.length > 1 && <span>共 {images.length} 张</span>}
            </div>
          ) : (
            <div className={`workImage generated ${tone}`}>
              <span>{mediaTypeLabel(work)}</span>
              <strong>{work.title}</strong>
            </div>
          )}
        </button>
      )}
      <div className="workBody">
        <div className="tagLine">
          <span>{workTypeLabel(work)}</span>
          {(work.tags || []).slice(0, 2).map((tag) => <span key={tag}>#{tag}</span>)}
          <span>{work.vote_count ?? 0} 票</span>
        </div>
        <h3>
          <button className="workTitleButton" onClick={onOpen} type="button">{work.title}</button>
        </h3>
        <p>{work.description}</p>
        {(work.link || attachment) && (
          <div className="workResources">
            {work.link && (
              <a className="workLink" href={work.link} rel="noreferrer" target="_blank">
                查看链接 ↗
              </a>
            )}
            {attachment && (
              <a className="workLink" href={attachment} rel="noreferrer" target="_blank">
                打开{mediaTypeLabel(work)} ↗
              </a>
            )}
          </div>
        )}
        <div className="workFooter">
          <div className="authorLine">
            <span className="avatar">{(work.author_name || "新").slice(0, 1)}</span>
            <strong>{work.author_name || "新员工"}</strong>
            <small>{work.status_label || "已发布"}</small>
          </div>
          <div className="actionRow">
            <button
              aria-label={`喜欢 ${work.title}，当前 ${work.like_count ?? 0} 个喜欢`}
              onClick={onLike}
              type="button"
            >
              ♡ {work.like_count ?? 0}
            </button>
            <button
              aria-label={`为 ${work.title} 投票，当前 ${work.vote_count ?? 0} 票`}
              onClick={onVote}
              type="button"
            >
              投票
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}

function MasonryGrid({ children, itemsKey }) {
  const gridRef = useRef(null);

  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid) {
      return undefined;
    }

    let animationFrame = 0;
    const resizeCards = () => {
      const rowHeight = Number.parseFloat(window.getComputedStyle(grid).gridAutoRows) || 4;
      const measurements = [...grid.children].map((card) => {
        const marginBottom = Number.parseFloat(window.getComputedStyle(card).marginBottom) || 0;
        const cardHeight = card.getBoundingClientRect().height;
        return {
          card,
          rowSpan: Math.max(1, Math.ceil((cardHeight + marginBottom) / rowHeight)),
        };
      });
      measurements.forEach(({ card, rowSpan }) => {
        card.style.gridRowEnd = `span ${rowSpan}`;
      });
    };
    const scheduleResize = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(resizeCards);
    };
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleResize);

    [...grid.children].forEach((card) => resizeObserver?.observe(card));
    resizeObserver?.observe(grid);
    window.addEventListener("resize", scheduleResize);
    resizeCards();

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", scheduleResize);
      resizeObserver?.disconnect();
    };
  }, [itemsKey]);

  return <div className="masonry" ref={gridRef}>{children}</div>;
}

function WorkImageCarousel({ images, title, onOpen }) {
  const carouselRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const imageSetKey = images.join("|");

  useEffect(() => {
    setActiveIndex(0);
    if (carouselRef.current) {
      carouselRef.current.scrollLeft = 0;
    }
  }, [imageSetKey]);

  function updateActiveIndex(event) {
    const { clientWidth, scrollLeft } = event.currentTarget;
    if (!clientWidth) return;
    const nextIndex = Math.min(images.length - 1, Math.max(0, Math.round(scrollLeft / clientWidth)));
    setActiveIndex(nextIndex);
  }

  function showImage(index) {
    const carousel = carouselRef.current;
    if (!carousel) return;
    carousel.scrollTo({ left: carousel.clientWidth * index, behavior: "smooth" });
    setActiveIndex(index);
  }

  return (
    <div className="workDetailCarouselShell">
      <div className="workDetailCarousel" onScroll={updateActiveIndex} ref={carouselRef}>
        {images.map((src, index) => (
          <button
            className="workDetailSlide"
            key={`${src}-${index}`}
            onClick={() => onOpen(index)}
            type="button"
            aria-label={`查看第 ${index + 1} 张大图`}
          >
            <img src={src} alt={`${title} ${index + 1}`} />
            <span className="workDetailZoomHint">点击查看大图</span>
          </button>
        ))}
      </div>
      {images.length > 1 && (
        <>
          <span className="workDetailImageCount">{activeIndex + 1}/{images.length}</span>
          <button
            className="workDetailCarouselArrow previous"
            disabled={activeIndex === 0}
            onClick={() => showImage(activeIndex - 1)}
            type="button"
            aria-label="上一张图片"
          >
            ‹
          </button>
          <button
            className="workDetailCarouselArrow next"
            disabled={activeIndex === images.length - 1}
            onClick={() => showImage(activeIndex + 1)}
            type="button"
            aria-label="下一张图片"
          >
            ›
          </button>
          <div className="workDetailDots" aria-label={`当前第 ${activeIndex + 1} 张，共 ${images.length} 张`}>
            {images.map((_, index) => (
              <button
                className={index === activeIndex ? "active" : ""}
                key={index}
                onClick={() => showImage(index)}
                type="button"
                aria-label={`查看第 ${index + 1} 张图片`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function WorkImageLightbox({ images, title, initialIndex, onClose }) {
  const carouselRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(initialIndex);

  useEffect(() => {
    const previousBodyOverflow = document.body.style.overflow;
    const previousPageOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    document.body.classList.add("workImageLightboxOpen");

    const frame = window.requestAnimationFrame(() => {
      const carousel = carouselRef.current;
      if (carousel) {
        carousel.scrollLeft = carousel.clientWidth * initialIndex;
      }
    });

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousPageOverflow;
      document.body.classList.remove("workImageLightboxOpen");
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [initialIndex, onClose]);

  function updateActiveIndex(event) {
    const { clientWidth, scrollLeft } = event.currentTarget;
    if (!clientWidth) return;
    setActiveIndex(Math.min(images.length - 1, Math.max(0, Math.round(scrollLeft / clientWidth))));
  }

  function showImage(index) {
    const carousel = carouselRef.current;
    if (!carousel) return;
    carousel.scrollTo({ left: carousel.clientWidth * index, behavior: "smooth" });
    setActiveIndex(index);
  }

  return (
    <div className="workImageLightbox" role="dialog" aria-modal="true" aria-label={`${title} 图片预览`}>
      <button className="workImageLightboxClose" onClick={onClose} type="button" aria-label="关闭大图">×</button>
      <div className="workImageLightboxCarousel" onScroll={updateActiveIndex} ref={carouselRef}>
        {images.map((src, index) => (
          <div className="workImageLightboxFrame" key={`${src}-large-${index}`}>
            <img src={src} alt={`${title} 大图 ${index + 1}`} />
          </div>
        ))}
      </div>
      {images.length > 1 && (
        <>
          <button
            className="workImageLightboxArrow previous"
            disabled={activeIndex === 0}
            onClick={() => showImage(activeIndex - 1)}
            type="button"
            aria-label="上一张图片"
          >
            ‹
          </button>
          <button
            className="workImageLightboxArrow next"
            disabled={activeIndex === images.length - 1}
            onClick={() => showImage(activeIndex + 1)}
            type="button"
            aria-label="下一张图片"
          >
            ›
          </button>
        </>
      )}
      <span className="workImageLightboxCount">{activeIndex + 1}/{images.length}</span>
      <small className="workImageLightboxHint">左右滑动切换图片，双指可缩放查看</small>
    </div>
  );
}

function ProtectedWorkDownloadButton({ work, className = "", children }) {
  const [downloading, setDownloading] = useState(false);

  async function downloadFile(event) {
    event.stopPropagation();
    setDownloading(true);
    try {
      const result = await api.workFile(work.id);
      const objectUrl = URL.createObjectURL(result.blob);
      const downloadLink = document.createElement("a");
      downloadLink.href = objectUrl;
      downloadLink.download = work.original_filename || `${work.title}.html`;
      document.body.appendChild(downloadLink);
      downloadLink.click();
      downloadLink.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (downloadError) {
      window.alert(downloadError.message || "文件下载失败，请稍后再试");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <button className={className} disabled={downloading} onClick={downloadFile} type="button">
      {downloading ? "准备下载..." : children}
    </button>
  );
}

function WorkDetailPage({ work, onBack, onLike, onVote, actionMessage, actionError }) {
  const galleryImages = getWorkImages(work);
  const fallbackImage = getWorkImage(work);
  const images = galleryImages.length > 0 ? galleryImages : (fallbackImage ? [fallbackImage] : []);
  const attachment = work.attachment;
  const isVideo = work.media_type === "video" && attachment;
  const isPdf = work.media_type === "pdf" && attachment;
  const isHtml = work.media_type === "html" && work.has_attachment;
  const showGeneratedCover = !isVideo && images.length === 0 && !isPdf;
  const hasVisualMedia = Boolean(isVideo || images.length > 0 || showGeneratedCover);
  const [lightboxIndex, setLightboxIndex] = useState(null);

  useEffect(() => {
    setLightboxIndex(null);
  }, [work.id]);

  return (
    <section className="workDetailPage">
      <div className="workDetailTop">
        <button onClick={onBack} type="button">‹ 返回</button>
        <span>作品详情</span>
      </div>
      {actionError && <p className="errorText interactionNotice" role="alert">{actionError}</p>}
      {actionMessage && <p aria-live="polite" className="successText interactionNotice" role="status">{actionMessage}</p>}
      <article className={`workDetailCard ${hasVisualMedia ? "" : "withoutVisual"}`}>
        {hasVisualMedia && (
          <div className="workDetailMedia">
            {isVideo ? (
              <video controls playsInline src={attachment} />
            ) : images.length > 0 ? (
              <WorkImageCarousel images={images} title={work.title} onOpen={setLightboxIndex} />
            ) : (
              <div className={`workDetailGenerated ${fallbackTones[work.id % fallbackTones.length]}`}>
                <span>{mediaTypeLabel(work)}</span>
                <strong>{work.title}</strong>
              </div>
            )}
          </div>
        )}
        <div className="workDetailBody">
          <div className="tagLine">
            <span>{workTypeLabel(work)}</span>
            <span>{mediaTypeLabel(work)}</span>
            {(work.tags || []).map((tag) => <span key={tag}>#{tag}</span>)}
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
          {isPdf && (
            <a className="workAttachmentCard" href={attachment} rel="noreferrer" target="_blank">
              <span className="workAttachmentIcon">PDF</span>
              <span className="workAttachmentInfo">
                <strong>{work.original_filename || `${work.title}.pdf`}</strong>
                <small>{work.file_size ? `${formatFileSize(work.file_size)} · ` : ""}点击查看附件</small>
              </span>
              <em>打开 ›</em>
            </a>
          )}
          {isHtml && (
            <ProtectedWorkDownloadButton className="workAttachmentCard htmlAttachment" work={work}>
              <span className="workAttachmentIcon">HTML</span>
              <span className="workAttachmentInfo">
                <strong>{work.original_filename || `${work.title}.html`}</strong>
                <small>{work.file_size ? `${formatFileSize(work.file_size)} · ` : ""}安全下载后在本地打开</small>
              </span>
              <em>下载 ›</em>
            </ProtectedWorkDownloadButton>
          )}
          <div className="workDetailLinks">
            {work.link && (
              <a href={work.link} rel="noreferrer" target="_blank">
                打开作品链接
              </a>
            )}
            {attachment && !isPdf && (
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
      {lightboxIndex !== null && (
        <WorkImageLightbox
          images={images}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          title={work.title}
        />
      )}
    </section>
  );
}

function CourseDetailModal({ course, onClose, onCourseChange, role }) {
  const [mindMapUrl, setMindMapUrl] = useState("");
  const [mindMapLoading, setMindMapLoading] = useState(false);
  const [mindMapError, setMindMapError] = useState("");
  const [mindMapPreviewOpen, setMindMapPreviewOpen] = useState(false);
  const [mindMapFile, setMindMapFile] = useState(null);
  const [resourceFiles, setResourceFiles] = useState([]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState("");
  const [downloadingId, setDownloadingId] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const previousBodyOverflow = document.body.style.overflow;
    const previousPageOverflow = document.documentElement.style.overflow;

    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";

    function closeOnEscape(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", closeOnEscape);

    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousPageOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";

    async function loadMindMap() {
      if (!course.has_mind_map) {
        setMindMapUrl("");
        setMindMapError("");
        return;
      }
      setMindMapLoading(true);
      setMindMapError("");
      try {
        const result = await api.courseMindMapFile(course.id);
        objectUrl = URL.createObjectURL(result.blob);
        if (!cancelled) setMindMapUrl(objectUrl);
      } catch (loadError) {
        if (!cancelled) setMindMapError(loadError.message || "思维导图加载失败");
      } finally {
        if (!cancelled) setMindMapLoading(false);
      }
    }

    loadMindMap();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [course.has_mind_map, course.id, course.mind_map_file_size]);

  function selectResources(event) {
    const selected = Array.from(event.target.files || []);
    const remainingCount = MAX_COURSE_RESOURCE_COUNT - course.resources.length - resourceFiles.length;
    if (selected.length > remainingCount) {
      setError(`每门课程最多保留 ${MAX_COURSE_RESOURCE_COUNT} 份资料，本次最多还能选择 ${Math.max(remainingCount, 0)} 份`);
    } else {
      setError("");
    }
    setResourceFiles((current) => {
      const merged = [...current];
      selected.forEach((file) => {
        const duplicate = merged.some((item) => (
          item.name === file.name && item.size === file.size && item.lastModified === file.lastModified
        ));
        if (!duplicate && course.resources.length + merged.length < MAX_COURSE_RESOURCE_COUNT) {
          merged.push(file);
        }
      });
      return merged;
    });
    event.target.value = "";
  }

  async function uploadMaterials(event) {
    event.preventDefault();
    if (!mindMapFile && resourceFiles.length === 0) {
      setError("请先选择思维导图或课程资料");
      return;
    }

    const formData = new FormData();
    if (mindMapFile) formData.append("mind_map", mindMapFile);
    resourceFiles.forEach((file) => formData.append("resources", file));
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const nextCourse = await api.uploadCourseMaterials(course.id, formData);
      onCourseChange?.(nextCourse);
      setMindMapFile(null);
      setResourceFiles([]);
      setMessage("课程资料已保存，学员现在可以查看了");
    } catch (uploadError) {
      setError(uploadError.message || "课程资料上传失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteMindMap() {
    if (!window.confirm("确定删除这张课程思维导图吗？")) return;
    setDeleting("mind-map");
    setMessage("");
    setError("");
    try {
      const nextCourse = await api.deleteCourseMindMap(course.id);
      onCourseChange?.(nextCourse);
      setMindMapPreviewOpen(false);
      setMessage("思维导图已删除");
    } catch (deleteError) {
      setError(deleteError.message || "思维导图删除失败");
    } finally {
      setDeleting("");
    }
  }

  async function deleteResource(resource) {
    if (!window.confirm(`确定删除“${resource.original_filename}”吗？`)) return;
    setDeleting(`resource-${resource.id}`);
    setMessage("");
    setError("");
    try {
      const nextCourse = await api.deleteCourseResource(resource.id);
      onCourseChange?.(nextCourse);
      setMessage("课程资料已删除");
    } catch (deleteError) {
      setError(deleteError.message || "课程资料删除失败");
    } finally {
      setDeleting("");
    }
  }

  async function openResource(resource) {
    const isPdf = resource.file_type === "pdf";
    const previewWindow = isPdf ? window.open("", "_blank") : null;
    setDownloadingId(resource.id);
    setError("");
    try {
      const result = await api.courseResourceFile(resource.id);
      const objectUrl = URL.createObjectURL(result.blob);
      if (isPdf) {
        if (previewWindow) {
          previewWindow.location.href = objectUrl;
        } else {
          window.location.href = objectUrl;
        }
      } else {
        const downloadLink = document.createElement("a");
        downloadLink.href = objectUrl;
        downloadLink.download = resource.original_filename;
        document.body.appendChild(downloadLink);
        downloadLink.click();
        downloadLink.remove();
      }
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    } catch (downloadError) {
      previewWindow?.close();
      setError(downloadError.message || "资料打开失败");
    } finally {
      setDownloadingId(null);
    }
  }

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
        <section className="courseMaterialSection">
          <div className="courseMaterialTitle">
            <div>
              <span>课程思维导图</span>
              <h3>先看全貌，再抓重点</h3>
            </div>
            {role === "admin" && course.has_mind_map && (
              <button disabled={deleting === "mind-map"} onClick={deleteMindMap} type="button">
                {deleting === "mind-map" ? "删除中..." : "删除"}
              </button>
            )}
          </div>
          {mindMapLoading ? (
            <div className="courseMaterialEmpty">正在加载思维导图...</div>
          ) : mindMapUrl ? (
            <button className="courseMindMap" onClick={() => setMindMapPreviewOpen(true)} type="button">
              <img alt={`${course.title}思维导图`} src={mindMapUrl} />
              <span>点击放大查看</span>
            </button>
          ) : (
            <div className="courseMaterialEmpty">{mindMapError || "这门课程暂未上传思维导图"}</div>
          )}
        </section>

        <section className="courseMaterialSection">
          <div className="courseMaterialTitle">
            <div>
              <span>课程资料</span>
              <h3>讲义与课堂课件</h3>
            </div>
            <strong>{course.resources.length} 份</strong>
          </div>
          {course.resources.length > 0 ? (
            <div className="courseResourceList">
              {course.resources.map((resource) => (
                <article key={resource.id}>
                  <span className={`courseResourceIcon ${resource.file_type}`}>{resource.file_type.toUpperCase()}</span>
                  <div>
                    <strong>{resource.original_filename}</strong>
                    <small>{formatFileSize(resource.file_size)} · {resource.file_type === "pdf" ? "支持在线查看" : "下载后查看"}</small>
                  </div>
                  <button disabled={downloadingId === resource.id} onClick={() => openResource(resource)} type="button">
                    {downloadingId === resource.id ? "读取中..." : resource.file_type === "pdf" ? "查看" : "下载"}
                  </button>
                  {role === "admin" && (
                    <button
                      className="courseResourceDelete"
                      disabled={deleting === `resource-${resource.id}`}
                      onClick={() => deleteResource(resource)}
                      type="button"
                    >
                      {deleting === `resource-${resource.id}` ? "删除中" : "删除"}
                    </button>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="courseMaterialEmpty">这门课程暂未上传资料</div>
          )}
        </section>

        {role === "admin" && (
          <form className="courseMaterialAdmin" onSubmit={uploadMaterials}>
            <div className="courseMaterialAdminHead">
              <span>管理员资料管理</span>
              <p>思维导图支持 JPG、PNG、WebP（10MB 内）；资料支持 PDF、PPTX（单个 100MB 内、单次 200MB 内，最多 10 份）。</p>
            </div>
            <label className="courseMaterialPicker">
              <span>{course.has_mind_map ? "替换思维导图" : "上传思维导图"}</span>
              <input
                accept={COURSE_MIND_MAP_ACCEPT}
                onChange={(event) => {
                  setMindMapFile(event.target.files?.[0] || null);
                  event.target.value = "";
                }}
                type="file"
              />
              <strong>{mindMapFile ? mindMapFile.name : "选择图片"}</strong>
            </label>
            <label className="courseMaterialPicker">
              <span>添加 PDF / PPTX</span>
              <input
                accept={COURSE_RESOURCE_ACCEPT}
                disabled={course.resources.length + resourceFiles.length >= MAX_COURSE_RESOURCE_COUNT}
                multiple
                onChange={selectResources}
                type="file"
              />
              <strong>选择资料</strong>
            </label>
            {resourceFiles.length > 0 && (
              <div className="coursePendingResources">
                {resourceFiles.map((file, index) => (
                  <div key={`${file.name}-${file.size}-${file.lastModified}`}>
                    <span>{index + 1}</span>
                    <strong>{file.name}</strong>
                    <small>{formatFileSize(file.size)}</small>
                    <button onClick={() => setResourceFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))} type="button">移除</button>
                  </div>
                ))}
              </div>
            )}
            <button className="courseMaterialSubmit" disabled={saving || (!mindMapFile && resourceFiles.length === 0)} type="submit">
              {saving ? "上传保存中..." : "保存课程资料"}
            </button>
          </form>
        )}
        {error && <p className="errorText courseMaterialNotice">{error}</p>}
        {message && <p className="successText courseMaterialNotice">{message}</p>}
      </article>
      {mindMapPreviewOpen && mindMapUrl && (
        <div className="courseMindMapLightbox" onClick={() => setMindMapPreviewOpen(false)} role="presentation">
          <button onClick={() => setMindMapPreviewOpen(false)} type="button" aria-label="关闭思维导图">×</button>
          <img alt={`${course.title}思维导图大图`} onClick={(event) => event.stopPropagation()} src={mindMapUrl} />
          <span>双指缩放或拖动查看细节</span>
        </div>
      )}
    </div>
  );
}

function StudentAttendancePanel() {
  const [attendance, setAttendance] = useState(null);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadAttendance({ quiet = false } = {}) {
    if (!quiet) setLoading(true);
    try {
      setAttendance(await api.attendanceToday());
      setError("");
    } catch (attendanceError) {
      setError(attendanceError.message || "签到状态加载失败");
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => {
    loadAttendance();
    const timer = window.setInterval(() => loadAttendance({ quiet: true }), 30000);
    return () => window.clearInterval(timer);
  }, []);

  async function submitAttendance(event) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    setError("");
    try {
      const result = await api.attendanceCheckIn(code);
      setMessage(result.detail || "签到成功");
      setCode("");
      await loadAttendance({ quiet: true });
    } catch (attendanceError) {
      setError(attendanceError.message || "签到失败，请检查签到码");
    } finally {
      setSubmitting(false);
    }
  }

  const currentSlot = attendance?.slots?.find((slot) => slot.slot === attendance.current_slot);
  const canSubmit = Boolean(currentSlot?.available && code.length === 4 && !submitting);

  return (
    <section className="studentAttendancePanel">
      <div className="attendancePanelHead">
        <div>
          <span>今日签到</span>
          <h2>{attendance?.date || "正在读取服务器时间"}</h2>
          <p>请在规定时间内完成签到，逾期不能补签。</p>
        </div>
        <strong>{currentSlot ? `${currentSlot.label} · ${currentSlot.window}` : "当前不在签到时段"}</strong>
      </div>

      {loading ? (
        <div className="loadingCard">正在加载签到状态...</div>
      ) : (
        <>
          <div className="attendanceSlotStrip">
            {(attendance?.slots || []).map((slot) => (
              <article className={`${slot.state} ${slot.slot === attendance.current_slot ? "current" : ""}`} key={slot.slot}>
                <span>{slot.label}</span>
                <strong>{slot.window}</strong>
                <em>{attendanceStateLabel(slot)}</em>
              </article>
            ))}
          </div>

          <form className="attendanceCheckInForm" onSubmit={submitAttendance}>
            <label>
              输入管理员公布的 4 位签到码
              <input
                aria-label="4 位签到码"
                autoComplete="one-time-code"
                disabled={!currentSlot?.available || currentSlot?.signed}
                inputMode="numeric"
                maxLength="4"
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 4))}
                pattern="\d{4}"
                placeholder="请输入 4 位数字"
                value={code}
              />
            </label>
            <button disabled={!canSubmit} type="submit">
              {submitting ? "签到中..." : currentSlot?.signed ? "本时段已签到" : currentSlot?.available ? "立即签到" : "签到暂未开放"}
            </button>
          </form>
        </>
      )}
      {error && <p className="errorText">{error}</p>}
      {message && <p className="successText">{message}</p>}
    </section>
  );
}

function CourseView({ camp, role }) {
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
    <div className="courseScene">
      {role === "student" && <StudentAttendancePanel />}
      <section className="sectionPanel">
        <div className="panelTitle">
          <span>课程表</span>
          <h2>{camp?.name || "当前培训期"}</h2>
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
        {selectedCourse && (
          <CourseDetailModal
            course={selectedCourse}
            onClose={() => setSelectedCourse(null)}
            onCourseChange={(nextCourse) => {
              setCourses((current) => current.map((item) => (item.id === nextCourse.id ? nextCourse : item)));
              setSelectedCourse(nextCourse);
            }}
            role={role}
          />
        )}
      </section>
    </div>
  );
}

function AdminAttendanceView() {
  const [selectedDate, setSelectedDate] = useState(() => dateInputValue(new Date()));
  const [overview, setOverview] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState("morning");
  const [listMode, setListMode] = useState("signed");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadOverview(date = selectedDate, { quiet = false } = {}) {
    if (!quiet) setLoading(true);
    try {
      const data = await api.adminAttendance(date);
      setOverview(data);
      setSelectedSlot((current) => {
        if (data.slots.some((slot) => slot.slot === current && slot.generated)) return current;
        return data.current_slot || data.slots.find((slot) => slot.generated)?.slot || "morning";
      });
      setError("");
    } catch (attendanceError) {
      setError(attendanceError.message || "签到数据加载失败");
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => {
    loadOverview(selectedDate);
    const timer = window.setInterval(() => loadOverview(selectedDate, { quiet: true }), 15000);
    return () => window.clearInterval(timer);
  }, [selectedDate]);

  async function generateCode() {
    setGenerating(true);
    setMessage("");
    setError("");
    try {
      const result = await api.generateAttendance();
      setMessage(`${result.slot_label}签到码已生成：${result.code}`);
    } catch (attendanceError) {
      setError(attendanceError.message || "签到码生成失败");
    } finally {
      await loadOverview(selectedDate, { quiet: true });
      setGenerating(false);
    }
  }

  const activeSlot = overview?.slots?.find((slot) => slot.slot === overview.current_slot);
  const currentData = overview?.slots?.find((slot) => slot.slot === selectedSlot) || overview?.slots?.[0];
  const displayedStudents = listMode === "signed" ? currentData?.records || [] : currentData?.absent_students || [];
  const canGenerate = Boolean(activeSlot && activeSlot.state === "active" && !activeSlot.generated);

  return (
    <section className="sectionPanel attendanceAdminScene">
      <div className="attendanceAdminHero">
        <div className="panelTitle">
          <span>仅管理员可见</span>
          <h2>签到管理台</h2>
          <p>系统按服务器时间开放签到；每个时段只能生成一次，所有管理员共享同一个签到码。</p>
        </div>
        <div className="attendanceAdminControls">
          <label>
            查看日期
            <input type="date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value)} />
          </label>
          <button disabled={!canGenerate || generating} onClick={generateCode} type="button">
            {generating ? "生成中..." : activeSlot?.generated ? "本时段已生成" : activeSlot ? `生成${activeSlot.label}签到码` : "当前不可生成"}
          </button>
        </div>
      </div>

      {error && <p className="errorText">{error}</p>}
      {message && <p className="successText">{message}</p>}

      {loading ? (
        <div className="loadingCard">正在加载签到管理数据...</div>
      ) : (
        <>
          <div className="attendanceMetrics">
            <strong>{overview?.student_count || 0}<span>学员总数</span></strong>
            <strong>{overview?.slots?.filter((slot) => slot.generated).length || 0}<span>今日已生成场次</span></strong>
            <strong>{overview?.slots?.reduce((total, slot) => total + slot.signed_count, 0) || 0}<span>当日签到人次</span></strong>
          </div>

          <div className="attendanceAdminSlots">
            {(overview?.slots || []).map((slot) => (
              <button
                className={`${selectedSlot === slot.slot ? "selected" : ""} ${slot.state}`}
                key={slot.slot}
                onClick={() => { setSelectedSlot(slot.slot); setListMode("signed"); }}
                type="button"
              >
                <span>{slot.label} · {slot.window}</span>
                <strong>{slot.generated ? slot.code : "未生成"}</strong>
                <small>
                  {slot.generated
                    ? `${slot.created_by || "管理员"}生成 · 已签到 ${slot.signed_count}/${overview.student_count}`
                    : attendanceAdminStateLabel(slot)}
                </small>
              </button>
            ))}
          </div>

          <section className="attendanceRoster">
            <div className="attendanceRosterHead">
              <div>
                <span>{currentData?.label} · {currentData?.window}</span>
                <h3>签到明细</h3>
              </div>
              <div>
                <button className={listMode === "signed" ? "active" : ""} onClick={() => setListMode("signed")} type="button">
                  已签到 {currentData?.signed_count || 0}
                </button>
                <button
                  className={listMode === "absent" ? "active" : ""}
                  disabled={!currentData?.generated}
                  onClick={() => setListMode("absent")}
                  type="button"
                >
                  未签到 {currentData?.absent_count ?? "-"}
                </button>
              </div>
            </div>

            {!currentData?.generated ? (
              <EmptyState title="本时段尚未生成签到码" text="只有当前签到时段可以生成，不能提前生成或逾期补生成。" />
            ) : displayedStudents.length === 0 ? (
              <EmptyState
                title={listMode === "signed" ? "暂时还没有学员签到" : "所有学员都已签到"}
                text="页面每 15 秒自动刷新一次，也可以切换日期或场次查看。"
              />
            ) : (
              <div className="attendanceTable" role="table">
                <div className="attendanceTableRow attendanceTableHeader" role="row">
                  <span>姓名</span>
                  <span>账号</span>
                  <span>{listMode === "signed" ? "签到时间" : "状态"}</span>
                </div>
                {displayedStudents.map((student) => (
                  <div className="attendanceTableRow" key={student.student_id} role="row">
                    <strong>{student.name}</strong>
                    <span>{student.username}</span>
                    <span>{listMode === "signed" ? formatFullDate(student.signed_at) : "未签到"}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}

function selectedAssetTypeLabel(file) {
  const lowerName = file.name.toLowerCase();
  if (file.type === "text/html" || lowerName.endsWith(".html") || lowerName.endsWith(".htm")) return "HTML";
  if (file.type === "application/pdf" || lowerName.endsWith(".pdf")) return "PDF";
  return "视频";
}

function WorkFilePicker({ asset, images, inputKey, onRemoveAsset, onRemoveImage, onSelect }) {
  const [previews, setPreviews] = useState([]);

  useEffect(() => {
    const nextPreviews = images.map((file) => ({ file, url: URL.createObjectURL(file) }));
    setPreviews(nextPreviews);
    return () => nextPreviews.forEach((preview) => URL.revokeObjectURL(preview.url));
  }, [images]);

  function selectFiles(event) {
    onSelect(event.target.files);
    event.target.value = "";
  }

  const pickerInput = (accept, label, multiple = false) => (
    <input
      accept={accept}
      aria-label={label}
      key={inputKey}
      multiple={multiple}
      onChange={selectFiles}
      type="file"
    />
  );

  return (
    <div className="workFilePicker">
      {previews.length > 0 ? (
        <>
          <div className="workImageSelectionGrid">
            {previews.map(({ file, url }, index) => (
              <article className="workImageSelectionItem" key={`${file.name}-${file.size}-${file.lastModified}-${index}`}>
                <img src={url} alt={`待上传图片 ${index + 1}：${file.name}`} />
                <span>{index + 1}</span>
                <button
                  aria-label={`删除第 ${index + 1} 张图片：${file.name}`}
                  onClick={() => onRemoveImage(index)}
                  type="button"
                >
                  ×
                </button>
                <small title={file.name}>{file.name}</small>
              </article>
            ))}
            {images.length < MAX_WORK_IMAGE_COUNT && (
              <label className="workImageAddTile">
                {pickerInput("image/*", "继续添加图片", true)}
                <strong>＋</strong>
                <span>继续添加</span>
              </label>
            )}
          </div>
          <div className="workImageSelectionSummary">
            <strong>已选择 {images.length} 张图片</strong>
            <span>还可以添加 {MAX_WORK_IMAGE_COUNT - images.length} 张，发布后按当前顺序展示</span>
          </div>
        </>
      ) : asset ? (
        <div className="workAssetSelection">
          <span>{selectedAssetTypeLabel(asset)}</span>
          <div>
            <strong>{asset.name}</strong>
            <small>{formatFileSize(asset.size)} · 已选择</small>
          </div>
          <button onClick={onRemoveAsset} type="button">移除</button>
        </div>
      ) : (
        <label className="workFileEmptyPicker">
          {pickerInput(WORK_FILE_ACCEPT, "选择作品图片或附件", true)}
          <strong>＋</strong>
          <span>添加图片或附件</span>
          <small>图片可以分多次继续添加</small>
        </label>
      )}
      {asset && (
        <label className="workAssetReplace">
          {pickerInput(WORK_FILE_ACCEPT, "更换作品附件")}
          更换文件
        </label>
      )}
      <small className="workFilePickerHelp">图片最多 10 张；HTML 最大 20MB；PDF、MP4、WebM、MOV 最大 500MB，附件每次只能上传 1 个。</small>
    </div>
  );
}

function PublishView({ camp }) {
  const initialForm = { title: "", work_type: "ai", tags: "", link: "", asset: null, images: [], description: "" };
  const [form, setForm] = useState(initialForm);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (!camp?.submission_open) {
      setError("当前不在作品投稿时间内。");
      return;
    }
    setSubmitting(true);
    setMessage("");
    setError("");

    try {
      const uploadId = form.asset && form.images.length === 0 ? await uploadWorkAsset(form.asset, setUploadProgress) : null;
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

  function updateFiles(fileList) {
    const nextFiles = mergeSelectedWorkFiles(form, fileList);
    if (nextFiles.error) {
      setError(nextFiles.error);
      return;
    }

    setError("");
    setForm((current) => ({ ...current, asset: nextFiles.asset, images: nextFiles.images }));
  }

  function removeImage(index) {
    setError("");
    setForm((current) => ({ ...current, images: current.images.filter((_, itemIndex) => itemIndex !== index) }));
  }

  function removeAsset() {
    setError("");
    updateField("asset", null);
  }

  return (
    <section className="creatorScene">
      <div className="creatorHero">
        <div className="panelTitle">
          <span>发布作品</span>
          <h2>提交一份新人作品</h2>
          <p>上传图片、PDF、HTML 或视频，提交后进入审核流，通过后正式出现在展示墙。</p>
        </div>
        <img src={mascotUiUpload} alt="" />
      </div>
      <form className="publishForm" onSubmit={submit}>
        {!camp?.submission_open && <p className="errorText">当前培训期投稿通道尚未开放或已经结束。</p>}
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
          作品标签
          <input
            onChange={(event) => updateField("tags", event.target.value)}
            placeholder="例如：AI 海报，流程 Demo（最多 5 个）"
            value={form.tags}
          />
          <small>用逗号、顿号或换行分隔，每个标签最多 20 个字符。</small>
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
        <div className="publishFileField">
          <div className="publishFieldLabel">
            <strong>上传文件</strong>
            <span>{form.images.length > 0 ? `${form.images.length}/${MAX_WORK_IMAGE_COUNT}` : "图片 / PDF / HTML / 视频"}</span>
          </div>
          <WorkFilePicker
            asset={form.asset}
            images={form.images}
            inputKey={fileInputKey}
            onRemoveAsset={removeAsset}
            onRemoveImage={removeImage}
            onSelect={updateFiles}
          />
        </div>
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
        <button disabled={submitting || !camp?.submission_open} type="submit">
          {submitting ? "提交中..." : "提交审核"}
        </button>
      </form>
    </section>
  );
}

function ReviewView() {
  const [items, setItems] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [filters, setFilters] = useState({ type: "all", mediaType: "all", author: "", ordering: "latest" });
  const [selectedIds, setSelectedIds] = useState([]);
  const [rejectingIds, setRejectingIds] = useState([]);
  const [rejectReason, setRejectReason] = useState("");
  const [previewWork, setPreviewWork] = useState(null);
  const [processing, setProcessing] = useState(false);

  async function loadPending() {
    setLoading(true);
    setError("");
    try {
      const nextItems = await api.pendingWorks({
        type: filters.type,
        mediaType: filters.mediaType,
        author: filters.author.trim(),
        ordering: filters.ordering === "oldest" ? "oldest" : "latest",
      });
      setItems(nextItems);
      setSelectedIds((current) => current.filter((id) => nextItems.some((item) => item.id === id)));
    } catch (reviewError) {
      setError(reviewError.message || "审核队列加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadReviewLogs() {
    try {
      setLogs(await api.reviewLogs());
    } catch {
      setLogs([]);
    }
  }

  useEffect(() => {
    loadPending();
  }, [filters]);

  useEffect(() => {
    loadReviewLogs();
  }, []);

  async function approve(id) {
    await reviewSingle(async () => api.approveWork(id), "已通过 1 个作品。");
  }

  async function deletePendingWork(work) {
    if (!window.confirm(`确定删除学员“${work.author_name || "未知学员"}”的作品“${work.title}”吗？删除后无法恢复。`)) {
      return;
    }
    await reviewSingle(async () => api.deleteWork(work.id), "作品已删除。");
    setPreviewWork((current) => (current?.id === work.id ? null : current));
  }

  async function reviewSingle(task, successText) {
    setProcessing(true);
    setError("");
    setMessage("");
    try {
      await task();
      setMessage(successText);
      await Promise.all([loadPending(), loadReviewLogs()]);
      notifyReviewQueueChanged();
    } catch (reviewError) {
      setError(reviewError.message || "审核操作失败");
    } finally {
      setProcessing(false);
    }
  }

  async function approveSelected() {
    if (selectedIds.length === 0) {
      return;
    }
    setProcessing(true);
    setError("");
    setMessage("");
    try {
      const result = await api.bulkReview({ action: "approve", ids: selectedIds });
      setMessage(`已通过 ${result.reviewed_count} 个作品。`);
      setSelectedIds([]);
      await Promise.all([loadPending(), loadReviewLogs()]);
      notifyReviewQueueChanged();
    } catch (reviewError) {
      setError(reviewError.message || "批量通过失败");
    } finally {
      setProcessing(false);
    }
  }

  function openReject(ids) {
    setRejectingIds(ids);
    setRejectReason("");
    setError("");
    setMessage("");
  }

  async function submitReject(event) {
    event.preventDefault();
    const reason = rejectReason.trim();
    if (!reason || rejectingIds.length === 0) {
      setError("请先选择打回作品并填写原因。");
      return;
    }

    setProcessing(true);
    setError("");
    setMessage("");
    try {
      if (rejectingIds.length === 1) {
        await api.rejectWork(rejectingIds[0], reason);
        setMessage("已打回 1 个作品。");
      } else {
        const result = await api.bulkReview({ action: "reject", ids: rejectingIds, reject_reason: reason });
        setMessage(`已打回 ${result.reviewed_count} 个作品。`);
      }
      setSelectedIds((current) => current.filter((id) => !rejectingIds.includes(id)));
      setRejectingIds([]);
      setRejectReason("");
      await Promise.all([loadPending(), loadReviewLogs()]);
      notifyReviewQueueChanged();
    } catch (reviewError) {
      setError(reviewError.message || "打回失败");
    } finally {
      setProcessing(false);
    }
  }

  function toggleSelection(id) {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function toggleAll() {
    if (selectedIds.length === items.length) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(items.map((item) => item.id));
  }

  const selectedItems = items.filter((item) => selectedIds.includes(item.id));
  const aiCount = items.filter((item) => item.work_type === "ai").length;
  const trainingCount = items.filter((item) => item.work_type === "training").length;
  const riskyCount = items.filter((item) => getReviewRisks(item).length > 0).length;

  return (
    <section className="sectionPanel reviewScene">
      <div className="reviewHero">
        <div className="panelTitle">
          <span>仅管理员可见</span>
          <h2>审核工作台</h2>
          <p>集中预览待审作品，先处理风险项，再批量完成审核。</p>
        </div>
        <img src={mascotUiSuccess} alt="" />
      </div>

      <div className="reviewMetrics">
        <strong>{items.length}<span>待处理</span></strong>
        <strong>{selectedIds.length}<span>已选中</span></strong>
        <strong>{riskyCount}<span>需关注</span></strong>
        <strong>{aiCount}/{trainingCount}<span>AI/培训</span></strong>
      </div>

      <div className="reviewToolbar">
        <label>
          作品类型
          <select value={filters.type} onChange={(event) => setFilters((current) => ({ ...current, type: event.target.value }))}>
            <option value="all">全部类型</option>
            <option value="ai">AI 作品</option>
            <option value="training">培训作品</option>
          </select>
        </label>
        <label>
          文件类型
          <select
            value={filters.mediaType}
            onChange={(event) => setFilters((current) => ({ ...current, mediaType: event.target.value }))}
          >
            <option value="all">全部文件</option>
            <option value="image">图片</option>
            <option value="pdf">PDF</option>
            <option value="html">HTML</option>
            <option value="video">视频</option>
            <option value="link">链接</option>
          </select>
        </label>
        <label>
          学员
          <input
            placeholder="搜索姓名或账号"
            value={filters.author}
            onChange={(event) => setFilters((current) => ({ ...current, author: event.target.value }))}
          />
        </label>
        <label>
          提交时间
          <select
            value={filters.ordering}
            onChange={(event) => setFilters((current) => ({ ...current, ordering: event.target.value }))}
          >
            <option value="latest">最新优先</option>
            <option value="oldest">最早优先</option>
          </select>
        </label>
      </div>

      <div className="reviewBatchBar">
        <button disabled={items.length === 0} onClick={toggleAll} type="button">
          {selectedIds.length === items.length && items.length > 0 ? "取消全选" : "全选本页"}
        </button>
        <button disabled={processing || selectedIds.length === 0} onClick={approveSelected} type="button">批量通过</button>
        <button disabled={processing || selectedIds.length === 0} onClick={() => openReject(selectedIds)} type="button">批量打回</button>
        <span>已选 {selectedIds.length} 个作品{selectedItems.length > 0 ? `：${selectedItems.map((item) => item.title).join("、")}` : ""}</span>
      </div>

      {error && <p className="errorText">{error}</p>}
      {message && <p className="successText">{message}</p>}

      {rejectingIds.length > 0 && (
        <form className="reviewRejectPanel" onSubmit={submitReject}>
          <div>
            <span>打回 {rejectingIds.length} 个作品</span>
            <strong>选择原因模板或直接填写</strong>
          </div>
          <div className="rejectTemplateGrid">
            {REVIEW_REJECT_TEMPLATES.map((template) => (
              <button key={template} onClick={() => setRejectReason(template)} type="button">
                {template}
              </button>
            ))}
          </div>
          <textarea
            required
            rows="3"
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
            placeholder="请输入给学员看的打回原因"
          />
          <div className="reviewRejectActions">
            <button disabled={processing} type="submit">确认打回</button>
            <button disabled={processing} onClick={() => setRejectingIds([])} type="button">取消</button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="loadingCard">正在加载审核队列...</div>
      ) : items.length === 0 ? (
        <EmptyState title="审核队列已清空" text="新的作品提交后会出现在这里。" />
      ) : (
        <div className="reviewList">
          {items.map((item) => (
            <article className="reviewCard" key={item.id}>
              <label className="reviewSelect">
                <input checked={selectedIds.includes(item.id)} onChange={() => toggleSelection(item.id)} type="checkbox" />
              </label>
              <button className="reviewPreviewButton" onClick={() => setPreviewWork(item)} type="button">
                <ReviewPreviewThumb work={item} />
              </button>
              <div className="reviewCardBody">
                <div className="reviewCardMeta">
                  <span>{workTypeLabel(item)}</span>
                  <span>{mediaTypeLabel(item)}</span>
                  <span>{formatWorkDate(item.created_at)} 提交</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.author_name} 提交 · {item.description}</p>
                <div className="reviewRiskList">
                  {getReviewRisks(item).map((risk) => (
                    <span key={risk}>{risk}</span>
                  ))}
                </div>
                <div className="reviewLinks">
                  {item.link && (
                    <a className="workLink" href={item.link} rel="noreferrer" target="_blank">
                      打开作品链接
                    </a>
                  )}
                  {item.attachment && (
                    <a className="workLink" href={item.attachment} rel="noreferrer" target="_blank">
                      打开附件
                    </a>
                  )}
                  {item.media_type === "html" && item.has_attachment && (
                    <ProtectedWorkDownloadButton className="workLink" work={item}>
                      安全下载 HTML
                    </ProtectedWorkDownloadButton>
                  )}
                </div>
              </div>
              <div className="reviewActions">
                <button disabled={processing} onClick={() => approve(item.id)} type="button">通过</button>
                <button disabled={processing} onClick={() => openReject([item.id])} type="button">打回</button>
                <button onClick={() => setPreviewWork(item)} type="button">预览</button>
                <button className="dangerButton" disabled={processing} onClick={() => deletePendingWork(item)} type="button">删除</button>
              </div>
            </article>
          ))}
        </div>
      )}

      <section className="reviewLogPanel">
        <div className="panelTitle">
          <span>审核日志</span>
          <h2>最近操作</h2>
        </div>
        {logs.length === 0 ? (
          <p>暂无审核记录。</p>
        ) : (
          <div className="reviewLogList">
            {logs.slice(0, 8).map((log) => (
              <article key={log.id}>
                <strong>{log.action_label} · {log.work_title}</strong>
                <span>{log.reviewer_name || log.reviewer_username || "管理员"} · {formatFullDate(log.created_at)}</span>
                {log.reason && <p>{log.reason}</p>}
              </article>
            ))}
          </div>
        )}
      </section>

      {previewWork && <ReviewPreviewModal work={previewWork} onClose={() => setPreviewWork(null)} />}
    </section>
  );
}

function ReviewPreviewThumb({ work }) {
  const image = getWorkImage(work);
  if (image) {
    return <img src={image} alt={work.title} />;
  }
  return (
    <span>
      <strong>{mediaTypeLabel(work)}</strong>
    </span>
  );
}

function ReviewPreviewModal({ work, onClose }) {
  const images = getWorkImages(work);
  const image = images[0] || getWorkImage(work);
  const attachment = work.attachment;
  const risks = getReviewRisks(work);

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <article className="reviewPreviewModal" onClick={(event) => event.stopPropagation()}>
        <div className="workDetailTop">
          <button onClick={onClose} type="button">‹ 关闭</button>
          <span>审核预览</span>
        </div>
        <div className="reviewPreviewGrid">
          <div className="reviewPreviewMedia">
            {work.media_type === "video" && attachment ? (
              <video controls src={attachment} />
            ) : work.media_type === "pdf" && attachment ? (
              <iframe src={attachment} title={work.title} />
            ) : images.length > 0 ? (
              <div className={`workDetailGallery count${Math.min(images.length, 4)}`}>
                {images.map((src, index) => (
                  <img src={src} alt={`${work.title} ${index + 1}`} key={`${src}-${index}`} />
                ))}
              </div>
            ) : image ? (
              <img src={image} alt={work.title} />
            ) : (
              <div className="workDetailGenerated blue">
                <span>{mediaTypeLabel(work)}</span>
                <strong>{work.title}</strong>
              </div>
            )}
          </div>
          <div className="reviewPreviewInfo">
            <div className="tagLine">
              <span>{workTypeLabel(work)}</span>
              <span>{mediaTypeLabel(work)}</span>
              {(work.tags || []).map((tag) => <span key={tag}>#{tag}</span>)}
              <span>{formatFileSize(work.file_size)}</span>
            </div>
            <h2>{work.title}</h2>
            <p>{work.description}</p>
            <div className="reviewRiskList">
              {risks.length === 0 ? <span>未发现明显风险</span> : risks.map((risk) => <span key={risk}>{risk}</span>)}
            </div>
            <div className="workDetailLinks">
              {work.link && <a href={work.link} rel="noreferrer" target="_blank">打开作品链接</a>}
              {attachment && <a href={attachment} rel="noreferrer" target="_blank">打开附件</a>}
              {work.media_type === "html" && work.has_attachment && (
                <ProtectedWorkDownloadButton work={work}>安全下载 HTML</ProtectedWorkDownloadButton>
              )}
            </div>
          </div>
        </div>
      </article>
    </div>
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
  const [deletingWorkId, setDeletingWorkId] = useState(null);
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

  async function deleteOwnWork(work) {
    if (!window.confirm(`确定删除自己的作品“${work.title}”吗？删除后无法恢复。`)) {
      return;
    }
    setDeletingWorkId(work.id);
    setMessage("");
    setError("");
    try {
      await api.deleteWork(work.id);
      setMyWorks((current) => current.filter((item) => item.id !== work.id));
      if (editingWorkId === work.id) {
        setEditingWorkId(null);
        setWorkDraft(null);
      }
      setMessage("自己的作品已删除。");
    } catch (deleteError) {
      setError(deleteError.message || "删除失败，请稍后重试");
    } finally {
      setDeletingWorkId(null);
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
        workplace: draft.workplace,
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
      tags: (work.tags || []).join("，"),
      asset: null,
      images: [],
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
      const uploadId = workDraft.asset && workDraft.images.length === 0
        ? await uploadWorkAsset(workDraft.asset, setWorkUploadProgress)
        : null;
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

  function updateWorkFiles(fileList) {
    const nextFiles = mergeSelectedWorkFiles(workDraft, fileList);
    if (nextFiles.error) {
      setError(nextFiles.error);
      return;
    }

    setError("");
    setWorkDraft((current) => ({ ...current, asset: nextFiles.asset, images: nextFiles.images }));
  }

  function removeWorkImage(index) {
    setError("");
    setWorkDraft((current) => ({ ...current, images: current.images.filter((_, itemIndex) => itemIndex !== index) }));
  }

  function removeWorkAsset() {
    setError("");
    updateWorkDraft("asset", null);
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
            <span>工作单位</span>
            <input value={draft.workplace || ""} onChange={(event) => setDraft({ ...draft, workplace: event.target.value })} />
          </label>
          <div className="profileEditRow profileReadOnlyRow">
            <span>小组</span>
            <div>
              <strong>{draft.training_group_label || "未分组"}</strong>
              <small>由管理员统一设置，学员不可修改</small>
            </div>
          </div>
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
            <select value={draft.zodiac || ""} onChange={(event) => setDraft({ ...draft, zodiac: event.target.value })}>
              <option value="">请选择星座</option>
              {zodiacOptions.map((zodiac) => (
                <option key={zodiac} value={zodiac}>{zodiac}</option>
              ))}
            </select>
          </label>
          <label className="profileEditRow">
            <span>MBTI</span>
            <select value={draft.mbti || ""} onChange={(event) => setDraft({ ...draft, mbti: event.target.value })}>
              <option value="">请选择 MBTI</option>
              {mbtiOptions.map((mbti) => (
                <option key={mbti} value={mbti}>{mbti}</option>
              ))}
            </select>
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
            <span>{profile.workplace || "未填写工作单位"}</span>
            <span>{genderLabel(profile.gender)}</span>
            <span>{profile.zodiac || "未填写星座"}</span>
            <span>{profile.mbti || "MBTI"}</span>
            <span>{profile.training_group_label || "未分组"}</span>
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
      {error && <p className="errorText profileMessage">{error}</p>}
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
                  <button
                    className="profileWorkDelete"
                    disabled={deletingWorkId === work.id}
                    onClick={() => deleteOwnWork(work)}
                    type="button"
                  >
                    {deletingWorkId === work.id ? "删除中..." : "删除自己的作品"}
                  </button>
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
                作品标签
                <input
                  placeholder="例如：AI 海报，流程 Demo"
                  value={workDraft.tags}
                  onChange={(event) => updateWorkDraft("tags", event.target.value)}
                />
                <small>最多 5 个标签，用逗号、顿号或换行分隔。</small>
              </label>
              <label>
                作品链接
                <input type="url" value={workDraft.link} onChange={(event) => updateWorkDraft("link", event.target.value)} />
              </label>
              <div className="publishFileField">
                <div className="publishFieldLabel">
                  <strong>重新上传文件</strong>
                  <span>{workDraft.images.length > 0 ? `${workDraft.images.length}/${MAX_WORK_IMAGE_COUNT}` : "图片 / PDF / HTML / 视频"}</span>
                </div>
                <WorkFilePicker
                  asset={workDraft.asset}
                  images={workDraft.images}
                  inputKey={workFileInputKey}
                  onRemoveAsset={removeWorkAsset}
                  onRemoveImage={removeWorkImage}
                  onSelect={updateWorkFiles}
                />
              </div>
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
  const [popularTags, setPopularTags] = useState([]);

  useEffect(() => {
    async function loadRailData() {
      const [list, tags] = await Promise.all([api.leaderboard(), api.popularTags()]);
      setFeatured(list[0] ?? null);
      setPopularTags(tags);
    }

    const refresh = () => loadRailData().catch(() => {
      setFeatured(null);
      setPopularTags([]);
    });
    refresh();
    window.addEventListener("reviewQueueChanged", refresh);
    const timer = window.setInterval(refresh, 60000);
    return () => {
      window.removeEventListener("reviewQueueChanged", refresh);
      window.clearInterval(timer);
    };
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
          {popularTags.length > 0 ? (
            popularTags.map((tag) => (
              <span key={tag.id} title={`${tag.work_count} 个已发布作品`}>
                #{tag.name} · {tag.work_count}
              </span>
            ))
          ) : (
            <span>暂无作品标签</span>
          )}
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
    window.addEventListener("reviewQueueChanged", loadPendingCount);
    const timer = window.setInterval(loadPendingCount, 15000);
    return () => {
      window.removeEventListener("reviewQueueChanged", loadPendingCount);
      window.clearInterval(timer);
    };
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

function notifyReviewQueueChanged() {
  window.dispatchEvent(new Event("reviewQueueChanged"));
}

function EmptyState({ title, text }) {
  return (
    <div className="emptyState">
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function buildTrainingDates(camp) {
  return (camp?.training_dates || []).map((value) => ({
    value,
    label: value.slice(5).replace("-", "/"),
    weekday: new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(new Date(`${value}T12:00:00`)),
  }));
}

function formatCampRange(camp) {
  if (!camp?.start_date || !camp?.end_date) {
    return "待公布";
  }
  return `${formatDate(camp.start_date)} - ${formatDate(camp.end_date)}`;
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

function formatFullDate(value) {
  if (!value) {
    return "刚刚";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dateInputValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function attendanceStateLabel(slot) {
  if (slot.signed) return "已签到";
  if (slot.state === "expired") return "已结束";
  if (slot.state === "upcoming") return "未开始";
  if (slot.available) return "可签到";
  return "等待管理员开放";
}

function attendanceAdminStateLabel(slot) {
  if (slot.state === "expired") return "本时段已结束";
  if (slot.state === "upcoming") return "未到生成时间";
  return "当前可生成签到码";
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
  return work.media_type_label || ({ image: "图片", pdf: "PDF", html: "HTML", video: "视频", link: "链接" }[work.media_type] ?? "作品文件");
}

function getWorkImage(work) {
  const galleryImages = getWorkImages(work);
  if (galleryImages.length > 0) {
    return galleryImages[0];
  }
  if (work.media_type === "image" && work.attachment) {
    return work.attachment;
  }
  return work.image || work.image_url || "";
}

function getWorkImages(work) {
  if (!Array.isArray(work.images)) {
    return [];
  }

  return work.images
    .map((item) => (typeof item === "string" ? item : item?.image))
    .filter(Boolean);
}

function genderLabel(value) {
  return genderOptions.find((option) => option.value === value)?.label ?? "未填写";
}

function scoreWork(work) {
  return (work.like_count ?? 0) + (work.vote_count ?? 0);
}

function formatFileSize(size) {
  const bytes = Number(size || 0);
  if (!bytes) {
    return "无文件";
  }
  if (bytes >= 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(bytes >= 100 * 1024 * 1024 ? 0 : 1)}MB`;
  }
  return `${Math.max(Math.round(bytes / 1024), 1)}KB`;
}

function getReviewRisks(work) {
  const risks = [];
  const hasFile = Boolean(work.has_attachment || work.attachment || work.image || getWorkImages(work).length > 0);
  const hasLink = Boolean(work.link);

  if (!hasFile && !hasLink) {
    risks.push("缺少作品文件或链接");
  }
  if ((work.description || "").trim().length < 20) {
    risks.push("介绍偏短");
  }
  if (work.media_type === "pdf" && !work.attachment) {
    risks.push("PDF 附件缺失");
  }
  if (work.media_type === "video" && !work.attachment) {
    risks.push("视频附件缺失");
  }
  if (work.media_type === "html" && !work.has_attachment) {
    risks.push("HTML 附件缺失");
  }
  if (work.file_size > 100 * 1024 * 1024) {
    risks.push(`大文件 ${formatFileSize(work.file_size)}`);
  }
  if (hasLink) {
    risks.push("需检查外部链接");
  }

  return risks;
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

function buildWorkFormData(work, uploadId = null) {
  const formData = new FormData();
  formData.append("title", work.title);
  formData.append("work_type", work.work_type);
  formData.append("link", work.link || "");
  formData.append("description", work.description);
  formData.append("tags", JSON.stringify(parseTagInput(work.tags)));
  if (uploadId) {
    formData.append("upload_id", uploadId);
  }
  (work.images || []).forEach((image) => {
    formData.append("images", image);
  });
  return formData;
}

function parseTagInput(value) {
  const values = Array.isArray(value) ? value : String(value || "").split(/[,，、\n]+/);
  const seen = new Set();
  return values
    .map((tag) => String(tag).trim().replace(/^#+/, "").trim())
    .filter((tag) => {
      const key = tag.toLocaleLowerCase();
      if (!tag || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function buildProfileFormData(profile) {
  const formData = new FormData();
  formData.append("name", profile.name || "");
  formData.append("workplace", profile.workplace || "");
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
