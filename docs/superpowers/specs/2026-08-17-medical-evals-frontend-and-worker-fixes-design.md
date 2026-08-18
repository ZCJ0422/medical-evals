# Medical Evals 前端与 Worker 修复设计

## 目标

修复重新测试中发现的可复现问题：前端中英文切换不完整、端到端测试与当前四步评测向导不一致，以及 Worker 从不同工作目录启动时无法定位 Registry 数据。

## 根因

1. `LocaleProvider` 的字典只覆盖少量 Dashboard/AppShell 文案；登录页、创建向导、列表、筛选、状态和结果相关组件仍使用硬编码英文。
2. 前端当前实现已经改为四步向导，并按数据集决定是否显示 Judge 字段；旧 E2E 仍按旧版单页表单和环境变量名填写字段。
3. `evaluator_adapter.py` 通过相对当前工作目录的 `registry/data/...` 读取数据；从 `backend/` 启动 API/Worker 时路径不存在。

## 设计

### 前端本地化

扩展现有 `i18n.tsx` 的字典，覆盖所有用户可见固定文案。组件通过 `t(key)` 获取文案；动态值（任务名、样本数、模型名）继续由组件拼接。`LocaleProvider` 使用 effect 同步 `<html lang>`，中文为 `zh-CN`，英文为 `en`。

Wizard 的数据集选择、模型配置、运行选项、复核、按钮、提示和校验错误全部使用字典。列表页、筛选器、空状态、删除提示和结果页沿用同一套字典，保证切换语言后页面不混杂主要英文文案。

### 测试契约

E2E 按当前 UI 行为重写：使用四步向导、`getByRole`/`getByLabel` 和稳定的 `name` 属性；MedQA 测试只填写目标模型和目标 API Key，HealthBench 测试额外填写 Judge 字段。测试断言队列表格行而不是旧版 `article` 结构，并单独覆盖语言切换后的创建页标题和字段。

### Worker 数据定位

新增项目根目录解析 helper，基于模块文件位置计算 `medical-evals/` 根目录，再拼接 `registry/data/...`。MedQA 和 HealthBench 加载器统一使用该 helper，测试通过临时改变 cwd 验证 cwd 独立性。

## 错误处理与边界

- 不改变 API key 加密、任务状态机和评分规则。
- 不把真实 API key 写入测试；E2E 只使用 `test-key` 等占位字符串。
- 评测创建后仍按当前逻辑进入 queued 状态；真实模型调用仍由 Worker 负责。
- Chromium 在当前沙箱中无法启动属于外部环境限制；代码层面提供可运行的 E2E 契约，验证时同时执行类型检查、构建、后端测试和可用浏览器的 E2E。

## 验收标准

- `npm run typecheck` 和 `npm run build` 通过。
- 后端完整测试通过，尤其是 4 个 Worker 失败用例。
- E2E 用例与当前向导字段和 DOM 结构一致。
- 中文模式下登录、Dashboard、创建向导、列表和筛选的主要用户可见文案为中文；英文模式保持英文。
- 从项目根目录和 `backend/` 目录运行 Worker 时均能读取内置 smoke 数据。
