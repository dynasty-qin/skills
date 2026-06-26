执行 wiki-router skill 的「查询」流程。

读取 `~/.claude/skills/wiki-router/SKILL.md`，按照「核心规则：回答问题前先查 wiki」执行：识别问题领域 → 找到对应 wiki → 读 index.md 定位相关页面 → 读取页面内容 → 以 wiki 为主要依据回答，用 `[[页面名]]` 引用来源。wiki 无相关内容时明确告知用户。所有逻辑以 SKILL.md 为准，本文件仅为触发入口。
