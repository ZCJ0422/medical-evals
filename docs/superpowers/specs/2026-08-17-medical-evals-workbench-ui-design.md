# Medical Evals Workbench UI 增强设计

## 目标

将当前“页面能用但信息单一”的前端升级为面向内部评测人员的医疗模型评测控制台，同时保留专业、克制、可信的产品气质。第一阶段只改造前端展示和交互，不扩大后端 API 范围；已有 API 不足时使用明确的空状态、推导指标或降级展示，不能伪造评测结果。

## 用户与成功标准

主要用户是负责配置、监控和复核模型评测的内部管理员。升级完成后，用户应能：

1. 登录后立即知道当前运行状态、近期评测和下一步操作。
2. 在任务页快速搜索、按状态筛选并定位某个评测。
3. 通过分步流程创建评测，理解哪些配置是必填、哪些配置会触发 Judge Model。
4. 在结果页快速判断总分、通过率、维度差异和失败原因，并生成报告。
5. 在 375px 窄屏和桌面宽屏下完成核心操作，键盘用户也能访问所有主要动作。

## 设计方向

采用“评测控制台型”为主、“向导式评测平台”为辅，并吸收最小必要的数据分析模块。

- 产品类型：内部 SaaS / 运营分析控制台。
- 视觉风格：Data-Dense Dashboard，深海蓝绿色品牌基底，浅色内容画布，语义化状态色。
- 信息密度：标准偏高；使用 8px spacing rhythm、稳定的卡片/表格/状态组件。
- 主操作：每页只有一个明确 primary CTA；危险操作使用独立的 destructive 样式。
- 动效：150–300ms 的 opacity/transform 过渡，仅用于状态变化、列表进入、按钮反馈和筛选切换；支持 `prefers-reduced-motion`。
- 图标：使用统一的 SVG 图标风格；不使用 emoji 作为结构性图标。若当前没有图标依赖，先使用内联 SVG 图标组件，避免引入不必要的运行时依赖。

## 页面结构

### 1. 应用壳层

桌面端使用持久侧边栏，包含品牌、Overview、Evaluations 和当前用户区；主内容区包含页面标题、面包屑/上下文信息和主操作。移动端将侧边栏收缩为顶部栏或横向导航，保留当前页面标题和关键 CTA。

侧边栏的 active 状态必须由 URL 路径决定；登录、退出和语言切换保持现有行为。所有深层页面保留返回任务列表的可见路径。

### 2. Overview 控制台

替换当前空状态首页，内容从上到下为：

- 欢迎区：页面标题、当前工作区说明、New evaluation 主按钮。
- KPI 卡片：Total runs、Running、Completed、Pass rate。没有任务时显示 `0` 和“Create your first evaluation”，不显示虚构趋势。
- Running now：运行中任务的状态、进度、模型和数据集；没有运行任务时显示可操作的空状态。
- Recent evaluations：最近任务列表，展示状态、完成度、分数（如 API 有结果）和 View results。
- Quick start：三步说明“选择数据集 → 配置模型 → 查看结果”，帮助首次使用者理解流程。

仪表盘数据优先复用 `/api/evaluations`；前端计算数量和运行中任务，不能为了图表新增虚假数据。

### 3. Evaluations 任务页

将当前纵向卡片列表改为“工具栏 + 可扫描任务表/响应式任务卡”：

- 顶部标题区和 New evaluation CTA。
- 搜索框：按任务名称、模型 ID、数据集 ID 和 task ID 过滤。
- 状态筛选：All、Queued、Running、Completed、Failed/Partial failed、Cancelled。
- 结果统计条：当前过滤结果数量和运行中数量。
- 桌面表格列：名称、Target、Judge、Dataset、Status、Progress、Created/Updated、Actions。
- 移动端每行折叠为卡片，优先展示名称、状态、进度和主要操作。
- 删除操作保留确认；删除成功使用可访问的 aria-live 成功反馈。运行中任务不展示误导性的删除后立即消失行为，遵循后端状态约束。

轮询继续保持 3 秒，但加载时使用保留布局的 skeleton/淡化状态，避免整个页面闪烁。

### 4. New evaluation 向导

将长表单拆成四步：

1. Dataset：选择数据集版本，显示样本数、是否需要 Judge Model 和简短说明。
2. Models：配置 Target Model；HealthBench 类数据集才展开 Judge Model 配置。
3. Run options：最大样本数等运行参数，说明 smoke test 和完整运行的区别。
4. Review & launch：展示只读配置摘要、敏感信息保护提示、preflight 检查结果和 Create evaluation。

向导提供 step indicator、Back/Next、当前步骤错误定位和返回后保留输入。API 提交仍沿用现有 preflight → create 顺序；API 错误在相关步骤内展示 cause + recovery action。

### 5. Results 结果页

结果页升级为分析摘要，而不是单纯数字列表：

- 页面头部：任务名称/ID、状态、数据集、模型摘要、Back 和 Generate report。
- KPI：Total score、Pass rate、Completed、Failed/Retry。
- Dimension scores：使用水平条形图样式展示百分比，同时保留可读的文本数值；提供表格语义，不能只依赖颜色。
- Error breakdown：按错误分类展示数量和比例，空状态明确说明没有记录错误。
- Run summary：样本完成情况、Judge 信息和生成时间；API 没有字段时隐藏该行而不是填写猜测值。
- Report action：生成报告时显示 loading、成功/失败状态，并提供可重复点击保护。

不引入第三方图表库；第一阶段使用可访问的 HTML/CSS horizontal bars 和数据列表，降低 bundle 和依赖复杂度。

## 组件与数据边界

优先抽取以下轻量组件，避免所有页面继续使用长单文件 JSX：

- `AppShell` / `PageHeader`
- `StatusBadge` / `ProgressBar`
- `MetricCard`
- `EmptyState` / `InlineAlert` / `Skeleton`
- `EvaluationFilters` / `EvaluationTable`
- `EvaluationWizard`
- `ScoreBars` / `ErrorBreakdown`

类型继续集中在 `frontend/lib/types.ts`，API 调用继续集中在 `frontend/lib/api.ts`。页面组件只负责组合和交互状态，不直接复制请求头、状态颜色或错误文案。新增前端推导类型必须与现有后端返回字段保持兼容。

## 响应式与无障碍

- 断点以 375 / 768 / 1024 / 1440 为验证目标。
- 所有按钮、输入和筛选控件最小可操作区域不低于 44px。
- 保留可见 focus ring、正确 label、`aria-live` 错误/成功反馈和顺序标题层级。
- 语义色不能作为唯一信息来源；状态必须同时显示文字。
- 所有异步区域提供 loading、empty、error、success 状态。
- 对 `prefers-reduced-motion: reduce` 禁用装饰性位移动画，只保留必要的状态变化。
- 移动端不产生横向滚动；表格在窄屏切换为卡片布局。

## 测试与验收

1. `npm run build` 和 `npm run typecheck` 通过。
2. Playwright 覆盖登录、Overview 空状态/有任务状态、任务搜索与筛选、向导前后退和结果页关键摘要。
3. 手工检查 375px、768px 和桌面宽度；覆盖键盘 Tab 顺序和 reduced motion。
4. 检查敏感 API key 不出现在页面内容、localStorage 或错误文案中。
5. 不改变后端接口契约；没有数据的指标必须降级为空状态或 0，而不是虚构趋势。

## 范围外

- 不新增模型供应商 SDK、数据库字段或后端统计接口。
- 不实现实时 WebSocket、复杂对比实验、用户权限体系或人工标注界面。
- 不引入重量级图表/设计系统依赖，除非现有实现无法满足可访问性或响应式要求。
