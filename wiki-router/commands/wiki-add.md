执行 wiki-router skill 的「单篇写入」流程。

读取 `~/.claude/skills/wiki-router/SKILL.md`。从用户输入中提取目标 wiki 和源文件路径。如用户未指定 wiki，按 SKILL.md 的分类规则自动判断。复制文件到对应 wiki 的 raw/，启动后台子 agent 按 CLAUDE.md 的 Ingest Workflow 消化。所有逻辑以 SKILL.md 为准，本文件仅为触发入口。
