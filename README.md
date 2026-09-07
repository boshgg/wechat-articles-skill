# 微信公众号文章-skill

商丘金蓬公众号的 Word 原稿到成稿流程：专业审查、最小修改、原图保真、Markdown、排版 Word、统一风格 HTML，以及逐篇验收和共享目录备份。

这是一个需要 AI/人工审查参与的 **Codex skill**，不是自动证明文章正确或自动群发的程序。默认采用用户截至 2026-09-07 的最新约定。

## 安装与调用

将仓库内容放在 `$CODEX_HOME/skills/wechat-articles`；未设置时通常为 `~/.codex/skills/wechat-articles`。重新载入技能后使用：

```text
使用 $wechat-articles，处理项目里的新文章。
```

也支持“重新审查这周文章”“只修公众号 HTML”“统一日期命名”等范围受限的请求。

入口是 [SKILL.md](SKILL.md)。项目路径与备份默认值在 [project-defaults.json](assets/project-defaults.json)，新环境使用 CLI 参数覆盖。公司固定介绍见 [company-closing.md](assets/company-closing.md)。

## 包含内容

- 最新审查边界、知识库优先规则及法规时效处理。
- 原文结构、图片字节、图注、作者及日期命名要求。
- `jinpeng-reference-v2` HTML 和 Word 生成器。
- Word 提取、发布文件机械校验、备份哈希验证工具。
- 手机/桌面浏览器检查和合成样例回归测试。

使用命令和工具限制见 [tooling.md](references/tooling.md)，完整验收见 [qa.md](references/qa.md)。Markdown 不是微信可直接识别的富文本，HTML 本地预览也不等于已完成公众号后台粘贴验证。

## 数据与权限

仓库不包含文章原稿、客户素材、知识库文件、索引数据库或凭据。脚本不会联网审查，也不会自动向公众号发布；本地审查、截图检查与后台实测由执行 skill 的代理在授权范围内完成。备份是独立显式命令，默认只向用户指定共享目录写入 HTML。
