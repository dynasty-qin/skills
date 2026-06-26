# Wiki Router — 多知识库路由 Skill

在任意对话中将资料分发到对应的 wiki 知识库，回答问题时主动参考 wiki 中的知识。

## 环境检测（每次启动必执行）

**第一条指令：读取 `F:\AI\skills\wiki-router\config.json`。**

若 `setupComplete` 为 `false` 或 config 不存在，进入**首次设置向导**（见下方）。设置完成前不做任何其他操作。

若 `setupComplete` 为 `true`，以 config 中的路径为准，跳过设置。

---

## 首次设置向导

按以下顺序逐步执行，每步等用户回复再继续：

### 第 1 步：Obsidian Vault 位置

```
📍 你的 Obsidian vault 根目录在哪里？

（例如：E:\MyVault）
```

用户输入后，验证路径存在且包含 `.obsidian` 子目录。不通过则要求重新输入。

### 第 2 步：Clippings 文件夹

```
📎 你的 Clippings（剪藏）文件夹在哪里？

通常在 vault 下叫 "Clippings" 或 "clips"。请确认：
- 已有：告诉我路径
- 还没有：是否需要安装 Obsidian Web Clipper 浏览器插件？
  Chrome: https://chromewebstore.google.com/detail/obsidian-web-clipper
```

验证路径存在。不存在则提示安装插件后再来。

### 第 3 步：环境检查

自动执行，无需用户输入：

```bash
git --version                          # 检测 Git
git ls-remote https://github.com/SamurAIGPT/llm-wiki-agent.git HEAD  # 检测 GitHub 连通性
```

汇报结果：
```
✅ Git: 已安装 (v2.x.x)
✅ GitHub: 可访问
⚠️  GitHub: 无法访问 — 需要手动下载 llm-wiki-agent
```

### 第 4 步：第一个知识库

```
📚 你想创建什么主题的知识库？

示例："AI技术"、"投资研究"、"读书笔记"
或者直接说"先不创建"跳过。
```

用户给出名称后：
1. `git clone https://github.com/SamurAIGPT/llm-wiki-agent.git "{vaultPath}\kb-{名称}"`
2. 确认 clone 成功

### 第 5 步：写入配置

将以上所有信息写入 `config.json`，`setupComplete` 设为 `true`。报告：

```
✅ Wiki Router 配置完成！

  Vault:    {vaultPath}
  Clips:    {clippingsFolder}
  Wiki:     kb-{名称}（名称）
  
  之后你可以：
  - 说"同步 clippings"来自动分类并消化新文章
  - 说"创建一个 XX 知识库"来新增知识库
  - 有任何 AI/技术问题，我会自动查你的 wiki 再回答
```

---

## 知识库发现规则

Skill 不维护硬编码的 wiki 列表。**每次运行时动态发现**：

扫描 `{vaultPath}\kb-*` 目录，满足以下条件视为有效 wiki：
- 目录名以 `kb-` 开头
- 包含 `CLAUDE.md` 文件
- 包含 `raw/` 子目录

用 find 命令：
```bash
find "{vaultPath}" -maxdepth 1 -type d -name "kb-*" -exec test -f "{}/CLAUDE.md" \; -print
```

发现结果即为当前可用的 wiki 列表。**名称从目录名自动提取**：`kb-AI知识` → `AI知识`。

---

## ⚠️ 核心规则：回答问题前先查 wiki

当用户提出的问题可能被某个 wiki 覆盖时，**必须先查 wiki 再回答**。

**查 wiki 的方式**：
1. 读 `{wiki}/wiki/index.md` 找到相关页面
2. 读具体页面获取详细内容
3. 以 wiki 内容为主要依据，用 `[[页面名]]` 格式引用来源
4. 如果 wiki 没有相关内容，明确告知后补充自身知识

**分类参考**（根据 wiki 目录名推断领域，非硬编码）：

| wiki 名称包含 | 匹配的问题 |
|--------------|-----------|
| AI、技术、Tech、LLM | AI、大模型、编程、Agent 等 |
| 投资、理财、基金、股票 | 投资、市场、行业分析 |
| 读书、阅读、书 | 书籍内容、作者观点 |

---

## 触发方式

**写入（加入资料）**：
```
"帮我把这篇文章加到 XX 知识库"
"这个 PDF 存到 XX wiki"
```

如果用户未指定目标 wiki，自动匹配（参见"智能同步"的分类逻辑）。

**查询（wiki 辅助回答）**：自动触发，无需用户显式指定。

**新增知识库**：
```
"新建一个 XX 知识库"
"创建一个关于 XX 的 wiki"
```

执行：`git clone llm-wiki-agent → {vaultPath}\kb-{名称}`，问用户要不要立刻同步相关文章进去。

---

## 智能同步流程

### 触发方式

```
"同步 clippings"
"/wiki-sync"
```

同步 = **新增 + 清理**，确保 wiki 与 raw/ 完全一致。

---

### 阶段一：发现新增 & 修改

#### 1.1 新增检测

对比 `{clippingsFolder}` 与所有 wiki 的 `raw/`，找出尚未复制的 .md 文件。

#### 1.2 修改检测（v2）

对 `raw/` 中**已存在**的文件，通过 SHA256 哈希判断内容是否变化。

**哈希记录文件**：每个 wiki 的 `raw/.ingested.json`，由 ingest agent 在成功消化后自动维护：

```json
{
  "某文章.md": "sha256:abc123...",
  "某报告.pdf": "sha256:def456..."
}
```

检测逻辑：

```bash
# 对 raw/ 中每个文件，计算当前哈希并与 .ingested.json 对比
# 文件在记录中但哈希不同 → 已修改
# 文件在记录中且哈希相同 → 无变化，跳过
# 文件不在记录中 → 新增（新 ingest）
```

修改检测到后，报告：

```
✏️  以下文件内容已变化：

  kb-AI知识:
    raw/某文章.md  →  上次: sha256:abc123  当前: sha256:xyz789
    raw/某报告.pdf  →  上次: sha256:def456  当前: sha256:ghi012

是否重新消化？这将：
  - 重新创建 source page（覆盖旧版）
  - 新发现的概念/实体会追加
  - 旧版独有的内容可能丢失

  [全部重新消化] [跳过] [逐个确认]
```

**逐篇分类**（新增和修改都需分类）：读标题和开头，与各 wiki 做语义匹配。

| 匹配结果 | 处理 |
|----------|------|
| 确定匹配 | 自动路由 |
| 模糊匹配 | 告知理由，让用户确认 |
| 无法匹配 | 暂停，列出选项（新建 wiki / 暂归 / 跳过） |

复制到对应 wiki 的 `raw/`（覆盖旧文件），等待阶段三统一消化。

#### 1.3 `.ingested.json` 维护规则

- **ingest agent 职责**：每成功消化一个源文件，追加/更新该文件在 `.ingested.json` 中的哈希
- **prune agent 职责**：级联删除时，同步移除 `.ingested.json` 中对应条目
- **sync 时**：不直接修改该文件，由子 agent 各自维护
- **如果文件不存在**：ingest agent 创建之，初始为空 `{}`

---

### 阶段二：发现清理

对**每个已创建的 wiki**，检测是否存在"raw/ 中已消失但 wiki/sources/ 中仍有对应页面"的源文件：

```bash
# 对比 raw/ 文件名 slug 与 wiki/sources/ 中的页面
# 找出 source page 存在但 raw 文件已不存在的 → 即为待清理页
```

如果发现待清理项，暂停并报告：

```
🧹 以下源文件已从 raw/ 中移除，对应 wiki 页面需要清理：

  kb-AI知识:
    wiki/sources/某旧文章.md  →  raw/ 中已无对应文件
    wiki/sources/过时报告.md  →  raw/ 中已无对应文件

级联影响：
  - 以上 source page 将被删除
  - index.md 中对应条目将被移除
  - 仅被这些来源引用的实体/概念页将被清理
  - 被多个来源共享的页面将保留，仅移除对此来源的引用
  - 其他页面中的死链将被修复

⚠️ 此操作不可逆。确认执行？
```

用户确认后，对每个待清理页执行级联删除：

1. **读 source page**，获取 `sources` 字段和页面内 `[[wikilinks]]`
2. **删除 source page 文件**
3. **更新 index.md**，移除对应条目
4. **检查关联实体/概念页**：
   - 读每个被引用的实体/概念页
   - 若该页面**仅被此来源**引用（sources 字段只有它）→ 标记删除
   - 若该页面被**多个来源共享** → 仅从 `sources` 字段中移除此来源，**页面保留**
5. **修复 wikilinks**：在其他 wiki 页面中搜索指向已删页面的 `[[链接]]`，移除或替换
6. **追加 log.md**：`## [日期] prune | <文件名>`
7. **不碰 raw/ 中的文件**（用户手动删除 raw/ 文件是清理的触发条件，skill 只清理 wiki/ 的对应产物）

> 此设计来源于 [[LLMWiki|LLM Wiki App]] 的 **Cascade Cleanup** 机制（共享实体保护 + Index 清理 + Wikilink 清理），补齐 [[LLM Wiki Agent]] 缺失的删除能力。

---

### 阶段三：统一消化

阶段一的新增/修改文件 + 阶段二的清理结果，并行启动子 agent：

**新增**：spawn 子 agent（`run_in_background: true`，cwd 为对应 wiki 目录），按 CLAUDE.md 的 Ingest Workflow 消化，完成后计算源文件 SHA256 更新 `raw/.ingested.json`。

**修改**：同上，但覆盖旧的 source page，追加 log 标注 `re-ingest`，更新 `.ingested.json` 中的哈希。

**清理**：spawn 子 agent（`run_in_background: true`，cwd 为对应 wiki 目录），按阶段二的级联删除步骤执行，同步移除 `.ingested.json` 中对应条目。

---

### 汇总报告

```
📂 Clippings: 12 篇
✅ 无变化:     5 篇

🆕 新增 3 篇 → 后台消化中：
  AI知识  ← 《SDD-RIPER团队指南》    Agent #1 ⏳

✏️ 修改 1 篇 → 重新消化中：
  AI知识  ← 《LoRA微调实践》          Agent #2 ⏳

🧹 清理 2 篇 → 后台执行中：
  AI知识  ← 移除《过时报告》           Agent #3 ⏳

⚠️ 未匹配 1 篇：
  《UX设计原则》 → 建议新建 wiki
```

---

### 子 agent 职责清单

| Agent 类型 | 触发条件 | 职责 |
|-----------|----------|------|
| Ingest（新增） | 新文件 | 标准 Ingest Workflow + 更新 `.ingested.json` |
| Ingest（修改） | 文件哈希变化 | 重新 Ingest（覆盖旧 source page）+ 更新 `.ingested.json` |
| Prune | raw/ 文件消失 | 级联删除 + 清理 `.ingested.json` |

---

## 单篇写入流程

```
"把这篇加到 XX 知识库"
"/wiki-add"
```

- 用户指定 wiki：直接路由
- 用户未指定 wiki：按分类逻辑自动匹配
- 指定 wiki 不存在：提醒 "还没有这个 wiki，要创建吗？" → clone

其余同同步流程。

---

## 查询流程

```
"XX 知识库里关于 YY 有什么？"
"/wiki-query"
```

1. 匹配 wiki（动态发现列表）
2. 读 `{wiki}/wiki/index.md` 定位页面
3. 读具体页面
4. 以 wiki 内容回答，引用 [[页面名]]

---

## 健康检查

```
"/wiki-health"
"检查 XX 知识库状态"
```

spawn 子 agent 到对应 wiki 运行 `python tools/health.py`。

---

## 注意事项

- 子 agent 只做 wiki 维护，不参与主对话讨论
- 所有 wiki 页面在 `{vaultPath}` 下，Obsidian 打开即可浏览
- 用 `find` 命令处理中文文件名，避免 bash 编码问题
- config.json 是唯一的环境配置文件，不存用户个人 wiki 列表
