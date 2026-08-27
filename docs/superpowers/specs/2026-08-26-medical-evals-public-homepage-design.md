# Medical Evals 公开首页设计方案

## 文档状态

- 状态：设计阶段，仅记录方案，暂不实现代码
- 目标页面：公开首页 `/`
- 产品：Medical Evals 医疗大语言模型评测框架
- 技术栈：Next.js 15、React 19、TypeScript
- 目标用户：医疗 AI 研究者、模型开发者、评测工程师和相关团队

## 1. 设计目标

公开首页的任务不是展示管理员运行状态，而是让未登录用户快速理解：

1. Medical Evals 是什么。
2. 它解决了什么问题。
3. 评测过程如何工作。
4. 用户可以从哪里阅读方法、查看项目和登录工作台。

首页应建立“开放、可复现、可审阅、面向医疗场景”的产品认知，避免看起来像普通后台系统、医院官网或泛 AI 营销页。

## 2. 视觉方向

### 2.1 整体气质

参考 Claude 官网的克制、留白和编辑式排版，但不复制其品牌、标志或具体布局。Medical Evals 采用更偏研究基础设施的视觉语言：安静、可信、清晰、有少量温度。

关键词：

- 编辑式科技品牌
- 研究型基础设施
- 自然、克制、可信
- 少量视觉隐喻
- 内容优先

### 2.2 色彩

主背景使用低饱和浅绿色，而不是上一版的米白或蓝色：

| 角色 | 建议颜色 | 用途 |
| --- | --- | --- |
| 页面背景 | `#EAF2E8` | 首屏和主页面背景 |
| 次级背景 | `#DCE9DC` | 特性条和流程区域 |
| 主文字 | `#242321` | 标题、导航、正文重点 |
| 辅助文字 | `#59634D` | 描述和说明文字 |
| 橄榄绿 | `#6D7259` | 品牌细节、图标、分隔线 |
| 暖橙色 | `#D97745` | CTA 下划线、流程节点、主视觉焦点 |
| 边界线 | `rgba(75, 86, 67, 0.22)` | 细分隔线和结构边界 |

浅绿色只做环境色，不能让正文和 CTA 失去对比度。实际实现时需要用对比度工具验证正文达到 WCAG AA 要求。

### 2.3 排版

- 主标题采用大字号中文标题，分成两行：`让医疗人工智能` / `经得起评测`。
- 标题使用 `text-wrap: balance`，避免窄屏出现孤立字符或难看的断行。
- 正文控制在约 65–75 个字符宽度以内。
- 标题、正文和导航使用清晰的字号层级，不使用过小的灰色文本传递核心信息。
- `Medical Evals` 作为品牌名保留原文，并设置 `translate="no"`。

## 3. 页面信息架构

```text
公开首页
├── 顶部导航
│   ├── Medical Evals 品牌
│   ├── 方法
│   ├── 基准
│   ├── 文档
│   ├── 项目
│   └── 登录
├── Hero 首屏
│   ├── 主标题
│   ├── 产品说明
│   ├── 开始评测
│   ├── 查看评测方法
│   └── 抽象主视觉
├── 核心价值条
│   ├── 可复现
│   ├── 可审阅
│   └── 面向医疗场景
├── 评测流程
│   └── 数据集 → 模型回答 → 评审与报告
├── 评测基准
│   ├── MedQA
│   └── HealthBench
├── 公开资源
│   ├── 评测方法
│   ├── 技术文档
│   └── 项目源码
├── 底部行动区
└── 页脚
```

## 4. 页面内容设计

### 4.1 顶部导航

导航保持轻量，不使用后台侧边栏或密集菜单。

- 品牌：`Medical Evals`
- 导航：`方法`、`基准`、`文档`、`项目`
- 右侧主要入口：`登录`

“登录”比“进入工作台”更符合公众网站的认知习惯。工作台是登录后的产品名称，不作为公开首页唯一入口的动词。

### 4.2 Hero 首屏

主标题：

> 让医疗人工智能经得起评测

说明文案：

> 开放、可复现、面向医疗大模型的评测框架

行动入口：

- 主入口：`开始评测`
- 次入口：`查看评测方法`

右侧主视觉使用橙色有机圆形与细线轨迹，表达从问题到证据的形成过程。它是装饰性视觉，不承载唯一信息，不使用医院照片、医生、听诊器或红十字符号。

### 4.3 核心价值条

使用三项短语建立产品认知：

- `可复现`
- `可审阅`
- `面向医疗场景`

不使用尚未被项目数据支持的用户数量、准确率、排名或机构 logo。

### 4.4 评测流程

标题：`从问题到证据`

三个步骤：

1. `数据集`：选择医学评测数据和版本。
2. `模型回答`：通过 OpenAI 兼容接口获取模型回答。
3. `评审与报告`：根据评测规则生成可审阅的结果和报告。

流程图的连线和编号只作为视觉辅助，所有步骤名称和说明必须以真实文本存在于 DOM 中。

### 4.5 评测基准

介绍项目已有的核心方向：

- `MedQA`：用于医学知识与选择题能力评估。
- `HealthBench`：用于开放式医疗回答和 rubric 评审。

每张内容卡提供“了解更多”或文档链接，不在首页虚构评测结果。

### 4.6 公开资源和底部行动区

公开资源包括：

- 评测方法
- 技术文档
- 项目源码

底部行动区文案建议：

> 从可复现的评测开始，建立更可信的医疗人工智能。

操作入口：`开始评测`、`登录`。

## 5. React 组件架构

公开首页不复用面向登录用户的 `AppShell`，也不在 `AppShell` 上增加 `isPublic`、`showSidebar` 等布尔参数。

### 5.1 组件树

```tsx
<PublicSiteShell>
  <PublicHeader>
    <Brand />
    <PublicNavigation />
    <HeaderActions>
      <LoginLink />
    </HeaderActions>
  </PublicHeader>

  <LandingPage>
    <HeroSection />
    <TrustStrip />
    <EvaluationStory />
    <BenchmarkSection />
    <PublicResources />
    <FinalCta />
  </LandingPage>

  <PublicFooter />
</PublicSiteShell>
```

### 5.2 组件职责

| 组件 | 职责 |
| --- | --- |
| `PublicSiteShell` | 公开页面容器、全局宽度和页面背景 |
| `PublicHeader` | 品牌、导航和登录入口 |
| `HeroSection` | 主标题、说明、CTA 和首屏视觉 |
| `TrustStrip` | 三项核心价值 |
| `EvaluationStory` | 评测流程叙事 |
| `BenchmarkSection` | MedQA、HealthBench 介绍 |
| `PublicResources` | 文档、方法和项目链接 |
| `FinalCta` | 页面底部转化入口 |
| `PublicFooter` | 项目链接、说明和版权信息 |

### 5.3 组合规则

- 使用 `children` 组合页面结构，不使用 `renderHeader`、`renderContent` 等 render props。
- 需要不同结构时创建显式组件，例如 `PublicHeader` 与 `AppHeader`，不通过多个 boolean prop 隐藏条件分支。
- 当前首页没有复杂共享状态，不引入 Zustand 或全局 Context。
- 文案集中放在 `frontend/lib/landing-content.ts`，组件只负责结构和展示。
- 动效组件只负责视觉动画，不负责页面数据或导航逻辑。

## 6. 动效和 UI 库

### 6.1 库选择

推荐使用 `motion`，用于：

- Hero 内容入场
- 橙色抽象图形的轻微漂移
- 章节进入视口时的淡入
- 用户可感知但不干扰阅读的层次变化

简单 hover、链接下划线和透明度变化继续使用 CSS，不为这些效果引入额外依赖。

不引入：

- `base-ui`：首页暂时没有复杂弹窗、菜单或选择器。
- `recharts`：公开首页不展示数据图表。
- `NumberFlow`：不展示动态统计数字。
- `zustand`：没有跨组件业务状态。
- `next-themes`：第一版暂不支持深色主题。

### 6.2 动效约束

- 只优先动画 `transform` 和 `opacity`。
- 禁止使用 `transition: all`。
- 支持 `prefers-reduced-motion`，关闭或简化装饰动画。
- 动效时长控制在约 150–300ms；首屏入场可以略长，但不能拖慢内容可读性。
- 橙色图形即使没有动画也必须完整表达页面意义之外的装饰，不影响信息获取。

## 7. 响应式设计

### 桌面端（≥ 1024px）

- 横向导航和右侧抽象主视觉并置。
- 主标题占据左侧主要视觉重量。
- 流程步骤使用横向排列。

### 平板端（768px–1023px）

- 缩小 Hero 标题和主视觉间距。
- 保留横向导航；必要时减少导航间距。
- 流程区域允许两列或改为纵向。

### 移动端（375px–767px）

- 导航折叠为菜单按钮，按钮必须有 `aria-label` 和可见焦点。
- Hero 改为单列，主视觉位于文案下方。
- CTA 触控区域最小 44px。
- 流程步骤纵向排列，禁止产生横向滚动。
- 保持标题和正文的清晰断行，不强制固定高度。

## 8. 无障碍与 Web Interface Guidelines 要求

- 根文档使用 `<html lang="zh-CN">`。
- 品牌名和代码标识设置 `translate="no"`。
- 使用语义化的 `<header>`、`<nav>`、`<main>`、`<section>`、`<footer>`。
- 页面提供跳转到主内容的 skip link。
- 所有导航和 CTA 使用 `<a>` 或 Next.js `<Link>`。
- 装饰性 SVG 设置 `aria-hidden="true"`；有意义的图片提供 `alt`。
- 图片设置明确的宽高，避免 CLS；非首屏图片使用懒加载。
- 标题层级从一个 `<h1>` 开始，后续使用合理的 `<h2>` / `<h3>`。
- 所有链接和按钮提供 hover、active、focus-visible 状态。
- 公开页面不使用只靠颜色表达含义的信息。
- 如果加入动画，必须支持 `prefers-reduced-motion`。
- 页面容器处理长文案和小屏宽度，避免横向滚动。
- 背景色、辅助文字和橙色 CTA 在实现阶段进行实际对比度测试。

## 9. SEO 与页面元数据

建议元数据：

- `title`：`Medical Evals｜医疗大模型评测框架`
- `description`：`面向医疗大语言模型的开放、可复现评测框架。`
- `lang`：`zh-CN`
- `theme-color`：与浅绿色页面背景一致

元数据应描述公开产品，不再使用“Internal medical language-model evaluation workspace”等内部工作台表述。

## 10. 文件边界

预计新增或调整：

```text
frontend/app/page.tsx
frontend/app/layout.tsx
frontend/app/globals.css
frontend/components/landing/public-site-shell.tsx
frontend/components/landing/public-header.tsx
frontend/components/landing/hero-section.tsx
frontend/components/landing/trust-strip.tsx
frontend/components/landing/evaluation-story.tsx
frontend/components/landing/benchmark-section.tsx
frontend/components/landing/public-resources.tsx
frontend/components/landing/final-cta.tsx
frontend/components/landing/public-footer.tsx
frontend/lib/landing-content.ts
```

明确不调整：

- `frontend/components/app-shell.tsx`
- 已登录工作台 `/app` 的信息架构
- 后端 API、评测队列、模型和 Judge 凭据处理
- 现有管理员评测页面的业务逻辑

## 11. 实现验收标准

### 内容

- 未登录访问 `/` 时可以理解产品定位。
- 首页全中文，品牌名 `Medical Evals` 保持原文。
- 顶部存在清晰的“登录”入口。
- “开始评测”和“查看评测方法”指向明确。
- 不出现未经项目数据支持的统计或机构背书。

### 视觉

- 页面整体为浅绿色调，橙色只作为重点强调色。
- 视觉重点是标题和叙事流程，而不是 KPI 卡片。
- 首屏在 1440px、1024px、768px 和 375px 下保持稳定布局。

### 工程与可访问性

- `npm run typecheck` 通过。
- `npm run build` 通过。
- Playwright 至少覆盖公开首页加载、导航链接、登录入口和移动端布局。
- 键盘可以访问所有导航和 CTA。
- `prefers-reduced-motion` 下无强制动画。
- 无横向滚动、图片 CLS、缺失 alt 或不可见焦点状态。

## 12. 当前决策摘要

1. 首页定位为面向公众的产品 Landing Page，不是管理员 Dashboard。
2. 视觉采用浅绿色编辑式科技风，保留橙色抽象主视觉。
3. 顶部入口使用“登录”，首屏 CTA 使用“开始评测”和“查看评测方法”。
4. 公开站点使用独立 `PublicSiteShell`，不改造已有 `AppShell`。
5. 交互动效推荐使用 `motion`，简单效果使用 CSS。
6. 当前只保存设计与架构，不进入代码实现。
