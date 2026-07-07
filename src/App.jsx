import { useMemo, useState } from "react";
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

const works = [
  {
    title: "AI 入职欢迎海报",
    author: "林小夏",
    meta: "ENFP · 天秤座",
    type: "AI 作品",
    likes: 238,
    votes: 96,
    image: communityCover,
    desc: "用 AI 生成视觉草图，再结合培训关键词完成新人欢迎海报。",
  },
  {
    title: "培训流程小程序原型",
    author: "周明",
    meta: "华南理工大学",
    type: "培训作品",
    likes: 186,
    votes: 88,
    tone: "blue",
    desc: "覆盖签到、任务提交、课程提醒和作品投票的轻量原型。",
  },
  {
    title: "部门知识地图",
    author: "陈安",
    meta: "武汉大学",
    type: "培训作品",
    likes: 142,
    votes: 71,
    image: galleryHero,
    desc: "把部门职责、协作对象和常用系统整理成一张上手地图。",
  },
  {
    title: "AI 头像实验集",
    author: "许一诺",
    meta: "同济大学",
    type: "AI 作品",
    likes: 119,
    votes: 52,
    tone: "violet",
    desc: "探索统一风格的新员工数字头像，用于个人主页展示。",
  },
  {
    title: "结业路演 Demo",
    author: "赵予",
    meta: "南京大学",
    type: "培训作品",
    likes: 98,
    votes: 47,
    tone: "orange",
    desc: "面向结业展示的产品方案和交互流程。",
  },
];

const courses = [
  { title: "企业文化与组织介绍", time: "07/06 09:00-11:00", status: "已结束", owner: "人力资源部" },
  { title: "AI 工具基础与提示词实践", time: "07/07 09:00-11:30", status: "进行中", owner: "数智化团队" },
  { title: "业务流程与协作规范", time: "07/08 14:00-16:00", status: "未开始", owner: "运营管理部" },
  { title: "结业路演与作品投票", time: "07/10 10:00-12:00", status: "未开始", owner: "培训项目组" },
];

const reviewItems = [
  { title: "新人训练复盘长图", author: "苏禾", type: "培训作品", note: "图片清晰，说明完整，待确认是否包含敏感信息。" },
  { title: "AI 产品海报三连", author: "唐可", type: "AI 作品", note: "创意完整，建议补充 AI 工具使用说明。" },
  { title: "业务流程卡片集", author: "陆然", type: "培训作品", note: "链接可访问，等待审核人员确认展示顺序。" },
];

const scheduleDays = [
  {
    date: "07/18",
    weekday: "周六",
    courses: [
      { time: "09:00-10:30", title: "开营仪式与破冰", teacher: "培训项目组", room: "报告厅", status: "已结束" },
      { time: "14:00-16:00", title: "企业文化导入", teacher: "人力资源部", room: "培训室 A", status: "已结束" },
    ],
  },
  {
    date: "07/19",
    weekday: "周日",
    courses: [
      { time: "09:30-11:30", title: "业务地图与组织协作", teacher: "运营管理部", room: "培训室 B", status: "未开始" },
    ],
  },
  {
    date: "07/20",
    weekday: "周一",
    courses: [
      { time: "09:00-11:30", title: "AI 工具基础与提示词实践", teacher: "数智化团队", room: "创新教室", status: "进行中" },
      { time: "15:00-16:30", title: "作品选题工作坊", teacher: "导师组", room: "协作区", status: "未开始" },
    ],
  },
  {
    date: "07/21",
    weekday: "周二",
    courses: [
      { time: "10:00-11:30", title: "产品思维与用户洞察", teacher: "产品中心", room: "培训室 A", status: "未开始" },
      { time: "14:00-17:00", title: "小组项目冲刺", teacher: "导师组", room: "项目室", status: "未开始" },
    ],
  },
  {
    date: "07/22",
    weekday: "周三",
    courses: [
      { time: "09:30-11:00", title: "数据安全与合规", teacher: "信息安全部", room: "培训室 B", status: "未开始" },
      { time: "15:00-16:00", title: "作品中期点评", teacher: "培训项目组", room: "报告厅", status: "未开始" },
    ],
  },
  {
    date: "07/23",
    weekday: "周四",
    courses: [
      { time: "09:30-11:30", title: "跨部门沟通演练", teacher: "组织发展部", room: "协作区", status: "未开始" },
      { time: "14:00-16:30", title: "AI 作品打磨", teacher: "数智化团队", room: "创新教室", status: "未开始" },
    ],
  },
  {
    date: "07/24",
    weekday: "周五",
    courses: [
      { time: "10:00-12:00", title: "结业路演彩排", teacher: "培训项目组", room: "报告厅", status: "未开始" },
    ],
  },
  {
    date: "07/25",
    weekday: "周六",
    courses: [
      { time: "09:30-11:30", title: "结业路演与作品投票", teacher: "评审团", room: "报告厅", status: "未开始" },
      { time: "14:00-15:00", title: "优秀作品颁奖", teacher: "培训项目组", room: "报告厅", status: "未开始" },
    ],
  },
];

function App() {
  const [role, setRole] = useState(null);
  const [activeTab, setActiveTab] = useState("feed");

  const tabs = role === "admin" ? adminTabs : studentTabs;

  function enter(nextRole) {
    setRole(nextRole);
    setActiveTab(nextRole === "admin" ? "review" : "feed");
  }

  if (!role) {
    return <LoginScreen onEnter={enter} />;
  }

  return (
    <div className={`app ${role === "admin" ? "adminMode" : ""}`}>
      <aside className="sideNav">
        <button className="brandButton" onClick={() => setRole(null)} type="button" aria-label="返回身份选择">
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
          <TopBar activeTab={activeTab} role={role} onLogout={() => setRole(null)} />
        )}
        {activeTab === "feed" && <FeedView role={role} />}
        {activeTab === "courses" && <CourseView />}
        {activeTab === "publish" && <PublishView />}
        {activeTab === "profile" && <ProfileView />}
        {activeTab === "review" && role === "admin" && <ReviewView />}
      </main>

      {role === "student" ? <StudentRail /> : <AdminRail />}
    </div>
  );
}

function LoginScreen({ onEnter }) {
  return (
    <main className="loginPage">
      <section className="loginHero">
        <div className="loginCopy">
          <span>New Hire Gallery</span>
          <h1>新人灵感墙</h1>
          <p>把培训作品、AI 创作和课程节奏整理成一个更像社区的展示空间。</p>
          <div className="loginActions">
            <button onClick={() => onEnter("student")} type="button">
              学员进入
            </button>
            <button onClick={() => onEnter("admin")} type="button">
              管理员审核
            </button>
          </div>
        </div>
        <div className="loginVisual">
          <img src={galleryHero} alt="新人展示墙视觉预览" />
          <div className="floatingNote">
            <strong>今日精选</strong>
            <span>AI 海报 · 流程 Demo · 知识地图</span>
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
        切换身份
      </button>
    </header>
  );
}

function FeedView({ role }) {
  const [selectedDay, setSelectedDay] = useState("07/20");
  const totalVotes = useMemo(() => works.reduce((sum, work) => sum + work.votes, 0), []);
  const rankedWorks = useMemo(
    () => [...works].sort((a, b) => b.votes + b.likes - (a.votes + a.likes)).slice(0, 5),
    [],
  );
  const activeSchedule = scheduleDays.find((day) => day.date === selectedDay) ?? scheduleDays[0];

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
          {scheduleDays.map((day) => (
            <button
              className={selectedDay === day.date ? "active" : ""}
              key={day.date}
              onClick={() => setSelectedDay(day.date)}
              type="button"
            >
              <strong>{day.date}</strong>
              <span>{day.weekday}</span>
            </button>
          ))}
        </div>
        <div className="scheduleTable" role="table" aria-label={`${activeSchedule.date} 课程表`}>
          <div className="scheduleRow scheduleHeader" role="row">
            <span>时间</span>
            <span>课程</span>
            <span>讲师 / 地点</span>
            <span>状态</span>
          </div>
          {activeSchedule.courses.map((course) => (
            <div className="scheduleRow" key={`${activeSchedule.date}-${course.time}-${course.title}`} role="row">
              <span>{course.time}</span>
              <strong>{course.title}</strong>
              <span>{course.teacher} · {course.room}</span>
              <em className={course.status}>{course.status}</em>
            </div>
          ))}
        </div>
      </div>

      <div className="rankingPanel">
        <div>
          <span>🔥 点赞 / 投票排行榜</span>
          <h2>本期 TOP 5</h2>
        </div>
        <div className="rankList">
          {rankedWorks.map((work, index) => (
            <article className="rankItem" key={work.title}>
              <strong>{index + 1}</strong>
              <div>
                <h3>{work.title}</h3>
                <p>{work.author} · {work.type}</p>
              </div>
              <span>{work.likes}赞 / {work.votes}票</span>
            </article>
          ))}
        </div>
        <div className="feedStats">
          <strong>{totalVotes}</strong>
          <span>累计投票</span>
        </div>
      </div>

      <div className="filterRow">
        <button type="button">推荐</button>
        <button type="button">培训作品</button>
        <button type="button">AI 作品</button>
        {role === "admin" && <button type="button">审核视角</button>}
      </div>

      <div className="masonry">
        {works.map((work, index) => (
          <WorkCard index={index} key={work.title} work={work} />
        ))}
      </div>
    </section>
  );
}

function WorkCard({ work, index }) {
  return (
    <article className={`workCard card${index}`}>
      {work.image ? (
        <img className="workImage" src={work.image} alt={work.title} />
      ) : (
        <div className={`workImage generated ${work.tone}`}>
          <span>{work.type}</span>
          <strong>{work.title}</strong>
        </div>
      )}
      <div className="workBody">
        <div className="tagLine">
          <span>{work.type}</span>
          <span>{work.votes} 票</span>
        </div>
        <h3>{work.title}</h3>
        <p>{work.desc}</p>
        <div className="authorLine">
          <span className="avatar">{work.author.slice(0, 1)}</span>
          <strong>{work.author}</strong>
          <small>{work.meta}</small>
        </div>
        <div className="actionRow">
          <button type="button">喜欢 {work.likes}</button>
          <button type="button">投票</button>
        </div>
      </div>
    </article>
  );
}

function CourseView() {
  return (
    <section className="sectionPanel">
      <div className="panelTitle">
        <span>课程表</span>
        <h2>这周的培训节奏</h2>
      </div>
      <div className="courseGrid">
        {courses.map((course) => (
          <article className={`courseCard ${course.status}`} key={course.title}>
            <span>{course.status}</span>
            <h3>{course.title}</h3>
            <p>{course.owner}</p>
            <strong>{course.time}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}

function PublishView() {
  return (
    <section className="creatorScene">
      <div className="panelTitle">
        <span>发布</span>
        <h2>提交一份新人作品</h2>
        <p>这里先做前端页面，后续接入上传、审核流和数据库。</p>
      </div>
      <form className="publishForm">
        <label>
          作品标题
          <input placeholder="例如：AI 入职欢迎海报" />
        </label>
        <label>
          作品类型
          <select defaultValue="ai">
            <option value="training">培训作品</option>
            <option value="ai">AI 作品</option>
          </select>
        </label>
        <label>
          作品链接
          <input placeholder="https://..." />
        </label>
        <label>
          作品介绍
          <textarea rows="5" placeholder="介绍作品背景、亮点和创作过程" />
        </label>
        <button type="button">提交审核</button>
      </form>
    </section>
  );
}

function ReviewView() {
  return (
    <section className="sectionPanel">
      <div className="panelTitle">
        <span>仅管理员可见</span>
        <h2>待审核内容</h2>
      </div>
      <div className="reviewList">
        {reviewItems.map((item) => (
          <article className="reviewCard" key={item.title}>
            <div>
              <span>{item.type}</span>
              <h3>{item.title}</h3>
              <p>{item.author} 提交 · {item.note}</p>
            </div>
            <div className="reviewActions">
              <button type="button">通过</button>
              <button type="button">打回</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ProfileView() {
  const [isEditing, setIsEditing] = useState(false);
  const [profile, setProfile] = useState({
    name: "新员工",
    school: "浙江大学",
    gender: "女",
    zodiac: "天秤座",
    mbti: "ENFP",
    bio: "正在把培训中的每一次练习，整理成可以被看见的作品。",
  });
  const [draft, setDraft] = useState(profile);
  const myWorks = works.slice(0, 4);

  function startEditing() {
    setDraft(profile);
    setIsEditing(true);
  }

  function saveProfile(event) {
    event.preventDefault();
    setProfile(draft);
    setIsEditing(false);
  }

  return (
    <section className="profileScene">
      <div className="profileCover">
        <img src={galleryHero} alt="个人主页封面" />
      </div>

      <div className="profileHome">
        <div className="profileAvatarBlock">
          <span className="bigAvatar">{profile.name.slice(0, 1) || "新"}</span>
          <button onClick={startEditing} type="button">
            编辑资料
          </button>
        </div>

        <div className="profileMainInfo">
          <span>个人主页</span>
          <h2>{profile.name}</h2>
          <p>{profile.bio}</p>
          <div className="profileMeta">
            <span>毕业院校：{profile.school}</span>
            <span>性别：{profile.gender}</span>
            <span>星座：{profile.zodiac}</span>
            <span>MBTI：{profile.mbti}</span>
          </div>
          <div className="profileStats">
            <strong>
              {myWorks.length}
              <span>作品</span>
            </strong>
            <strong>
              714
              <span>热度</span>
            </strong>
            <strong>
              96
              <span>获票</span>
            </strong>
          </div>
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
              <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label>
              毕业院校
              <input value={draft.school} onChange={(event) => setDraft({ ...draft, school: event.target.value })} />
            </label>
            <label>
              性别
              <select value={draft.gender} onChange={(event) => setDraft({ ...draft, gender: event.target.value })}>
                <option>女</option>
                <option>男</option>
                <option>其他</option>
                <option>未填写</option>
              </select>
            </label>
            <label>
              星座
              <input value={draft.zodiac} onChange={(event) => setDraft({ ...draft, zodiac: event.target.value })} />
            </label>
            <label>
              MBTI
              <input value={draft.mbti} onChange={(event) => setDraft({ ...draft, mbti: event.target.value.toUpperCase() })} />
            </label>
            <label>
              个人简介
              <textarea value={draft.bio} rows="4" onChange={(event) => setDraft({ ...draft, bio: event.target.value })} />
            </label>
          </div>
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
          <button type="button">已发布</button>
        </div>
        <div className="profileWorkGrid">
          {myWorks.map((work, index) => (
            <article className="profileWorkCard" key={work.title}>
              {work.image ? (
                <img src={work.image} alt={work.title} />
              ) : (
                <div className={`profileWorkPoster ${work.tone}`}>
                  <span>{work.type}</span>
                </div>
              )}
              <h4>{work.title}</h4>
              <p>{work.likes} 喜欢 · {work.votes} 票</p>
              {index === 0 && <strong>置顶</strong>}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function StudentRail() {
  return (
    <aside className="rightRail">
      <section className="featureCard">
        <img src={communityCover} alt="精选作品封面" />
        <div>
          <span>本周精选</span>
          <h2>AI 入职欢迎海报</h2>
          <p>238 喜欢 · 96 票</p>
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
  return (
    <aside className="rightRail">
      <section className="adminSummary">
        <span>待处理</span>
        <strong>3</strong>
        <p>作品正在等待审核</p>
      </section>
      <section className="topicCard">
        <h2>审核规则</h2>
        <p>确认作品链接可访问、图片无敏感信息、介绍内容完整后再通过。</p>
      </section>
    </aside>
  );
}

export default App;
