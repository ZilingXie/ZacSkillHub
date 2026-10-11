# 小红书适配协议

本文件把 Link Study 与 Hermes 的 `xiaohongshu` Skill / `xhs` CLI 连接起来。当前参考基线为 Hermes `xiaohongshu` 0.8.9；上游 Skill 声明为 MIT，公开入口为：

- Skill：<https://github.com/kyalpha313/xhs-cli-skill>
- CLI：<https://github.com/kyalpha313/xhs-cli-headless>

Link Study 不复制 Hermes 私有配置、账号、cookie、机器路径或远端工具。当前环境必须先检查实际可用的 Skill、工具或 `xhs` 命令，再执行路由。

## URL 触发

以下输入按小红书材料处理：

- `xhslink.com` 短链接；
- `xiaohongshu.com/explore/` 笔记链接；
- `xiaohongshu.com/discovery/` 发现链接；
- 用户明确说“小红书”“红书”“XHS”或“RedNote”。

## 路由优先级

| 意图 | 默认适配层 | 只读 CLI 入口 |
| --- | --- | --- |
| 读取一条笔记 | `xhs-read` | `xhs read <note_id_or_url>` |
| 读取评论 | `xhs-read` | `xhs comments <note_id_or_url>` |
| 搜索候选笔记 | `xhs-search` | `xhs search <query>` |
| 搜索用户/话题/热榜 | `xhs-search` | `xhs search-user`, `xhs topics`, `xhs hot` |
| 检查登录状态 | `xhs-auth` | `xhs status` 或 `xhs auth doctor` |
| 多条内容整理 | `xhs-ops` | 先 `search/read`，再整理 |

在 Hermes/Yuanbao 这类提供 `xhs_read` 的环境，用户只给小红书链接并要求阅读时，优先调用该只读工具；不要先用普通网页抓取或浏览器猜测正文。若当前环境没有 `xhs_read`，才按本环境 Skill 的说明使用 `xhs read`；两者都不可用时，索取正文或明确标记不可读。

## 证据记录

读取结果至少记录：标题、原始 URL 或 note id、作者（若工具返回）、发布时间（若工具返回）、正文/图片文字/评论的可见范围、获取时间、登录或风控限制。分别标注：

- 笔记作者的陈述；
- 评论者观点；
- 外部核验结果；
- Link Study 的推论；
- 无法确认的内容。

图片、视频或评论未返回时，不用标题、互动量或搜索摘要补写正文。原文被登录态、地域或风控截断时，报告中直接写明截断位置。

## 能力状态

把 XHS 能力分成三类：

- `supported`：当前环境和 CLI 明确支持，可路由；
- `hidden`：上游保留但不进入默认路由，例如发布或某些登录方式；
- `blocked`：已知失败或当前不承诺，例如 `delete`、`sub-comments`、`user`、`user-posts`、`favorites`、`likes`、`notifications`。

不要为了“试试看”静默调用 `blocked` 命令。收藏专辑优先考虑 `board`，新消息优先考虑 `unread`；用户主页和发帖能力不作额外承诺。

## 安全边界

- `like`、`favorite`、`comment`、`reply`、`follow` 及其撤销/删除操作均为写操作，必须在执行前确认目标、参数和时机。
- 读取或搜索不等于允许互动，不因为用户说“分析这篇”就执行社交操作。
- 未登录或会话失效时，先走 `xhs-auth` 的诊断路径，不盲目重试业务命令。
- 不把 cookie、令牌、二维码内容或认证文件写进报告、Skill 或 Git 仓库。
- 不批量扩展用户未明确指定的笔记、用户或互动目标。

## 输出衔接

XHS 读取完成后，回到 Link Study 的通用报告结构：来源、原文主张、证据、视角判断、实质分歧、对当前工作的意义、限制和下一步验证。若只返回了原始 CLI 结果，不能声称“围读完成”。
