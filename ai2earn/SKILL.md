# 社交媒体互动任务自动化

自动完成 AiToEarn 平台互动任务的全流程 Skill。支持小红书（XHS）和抖音（Douyin）。

## 前置配置（首次使用必须）

本 Skill 依赖两个 MCP Server。如果当前会话中 `mcp__aitoearn__*` 或 `mcp__chrome-devtools__*` 工具不可用，按以下步骤操作：

### 1. 在当前工作目录创建 `.mcp.json`

```json
{
  "mcpServers": {
    "aitoearn": {
      "type": "http",
      "url": "https://aitoearn.cn/api/unified/mcp",
      "headers": {
        "x-api-key": "${AITO_EARN_API_KEY}"
      }
    },
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

### 2. 重启 Claude Code 会话

`.mcp.json` 中的 MCP Server 只在会话启动时加载。配置完成后需**开启新会话**才能看到 `mcp__aitoearn__*` 和 `mcp__chrome-devtools__*` 工具。

### 3. 前置条件

- `chrome-devtools` MCP 需要 Chrome 浏览器正在运行，且开启了远程调试：`--remote-debugging-port=9222`
- `aitoearn` MCP 只需要网络连通 `https://aitoearn.cn`

---

## 触发条件

用户要求：
- "抢单做任务"
- "自动完成互动任务"
- "做 XHS/抖音 任务"
- "自动接单"

## 支持的任务类型

| 类型 | `type` | 支持平台 | 自动化方式 |
|------|--------|---------|-----------|
| 互动任务 | `interaction` | XHS, 抖音 | Chrome MCP 操作平台页面 → 截图 → MCP 提交 |
| CPE 推广任务 | `promotion` (CPE) | XHS | Chrome MCP 操作 aitoearn.cn 发布按钮 → 平台自动发布 |

**注意**：`sample`（需收货地址）、`brand_comment`（需特定内容）、`follow_account`（仅关注）不支持自动化。

## 所需 MCP 工具

| MCP Server | 用途 |
|-----------|------|
| `aitoearn` | 任务市场浏览、接单、任务详情、提交截图 |
| `chrome-devtools` | 浏览器自动化：导航、点击、输入、截图、上传 |

## 关键常量

- **API Base**: `https://aitoearn.cn`
- **API Key**: `ak_4XHJXNoWCd51PWAW0orOD6lFl68IE2J5JPu55SM61RZklbGx`
- **截图保存路径**: `$TMPDIR/task_screenshot.png`

---

# 一、互动任务流程 (`type: "interaction"`)

## 🚫 接受前确认

**接受任务前必须确认 `type === "interaction"`。** promotion 任务走第二部分流程（仅限 XHS 平台），且需人工确认能力。

## 阶段 0：前置检查（并行）

**0.1 检查已接任务数量**

```
mcp__aitoearn__listMyUserTasks: { status: "doing", pageSize: 10 }
```

如果已有 ≥ 5 个 `doing` 状态任务，先处理已接任务而非再接新任务。

**0.2 获取账号粉丝数**

```
mcp__aitoearn__getAllAccounts
```

记录各平台账号的粉丝数，用于后续过滤。

## 阶段 1：探索任务市场

```
mcp__aitoearn__listTaskMarket:
  platform: "xhs" | "douyin"  // 用户指定平台，或两个都查
  type: "interaction"
  pageSize: 20
```

**任务筛选规则（按优先级）**：

1. ⛔ **一票否决**：`acceptRules.fansNum > 用户粉丝数` → 直接跳过
2. ⛔ **去重**：已在 `listMyUserTasks` 中出现过的 `taskId` → 跳过
3. ⛔ **避免 follow**：优先选择 `interactionActions` 不含 `follow` 的任务（降低平台风控风险）
4. ✅ **优先选择**：`acceptRules` 为空或仅含 `fansNum ≤ 用户粉丝数`
5. ✅ **优先选择**：`currentRecruits < maxRecruits`（还有名额）
6. ✅ **优先选择**：`reward >= 15`（佣金合理）

**如果没有符合条件的任务**：告知用户当前无可用任务，列出被过滤的任务及原因。

## 阶段 2：接受任务

```
mcp__aitoearn__acceptTask:
  taskId: "<选中的任务ID>"
```

成功后记录返回的 `userTaskId`。若返回错误（如粉丝数不足），回到阶段 1 尝试下一个候选。

## 阶段 3：获取任务详情并导航

```
mcp__aitoearn__getMyUserTaskDetail:
  userTaskId: "<userTaskId>"
```

从返回数据中提取：
- `task.workLink` — 目标页面 URL
- `task.interactionActions` — 需要执行的操作（`like`, `collect`, `comment`, `follow`）
- `task.taskData.accountType` — 平台类型（`xhs` 或 `douyin`），决定后续交互方式

**导航到目标页面：**

```
mcp__chrome-devtools__navigate_page:
  type: "url"
  url: "<workLink>"
```

短链接（`xhslink.com`、`v.douyin.com`）会自动重定向。

## 阶段 4：页面交互

### 4.1 平台检测与策略选择

根据 `task.taskData.accountType` 确定交互策略：

| 平台 | accountType | 按钮选择器 | 评论输入方式 |
|------|------------|-----------|------------|
| 小红书 | `xhs` | CSS class (`.like-wrapper`, `.collect-wrapper`) | 点击输入框 → 输入 → 点击发送按钮 |
| 抖音 | `douyin` | `data-e2e` 属性 | fill combobox → press Enter |

### 4.2 获取页面状态

先截图 + 读页面了解笔记内容和当前交互状态：

```
mcp__chrome-devtools__take_screenshot
mcp__chrome-devtools__take_snapshot
```

### 4.3 检查交互状态

#### 小红书 (XHS)

用 `evaluate_script` 检查按钮状态：

```javascript
() => {
  const result = {};
  const engageBar = document.querySelector('.engage-bar');
  if (!engageBar) { result.error = 'no engage bar'; return result; }
  
  const svgUses = engageBar.querySelectorAll('svg use');
  svgUses.forEach(use => {
    const href = use.getAttribute('href') || use.getAttribute('xlink:href') || '';
    if (href.startsWith('#')) result[href] = true;
  });
  
  // 检查关注按钮
  const followBtn = document.querySelector('.follow-button, [class*="follow-btn"]');
  if (followBtn) result.followText = followBtn.textContent?.trim();
  
  // 获取笔记内容用于评论生成
  const title = document.querySelector('.title, [class*="title"], .note-title, h1')?.textContent?.trim();
  const desc = document.querySelector('.desc, [class*="desc"], .note-text, [class*="note-text"]')?.textContent?.trim();
  result.title = title || desc || '';
  
  return result;
}
```

图标含义：
- `#like` → 未点赞 / `#liked` → 已点赞
- `#collect` → 未收藏 / `#collected` → 已收藏
- `#chat` → 评论按钮存在
- `followText: "关注"` → 未关注 / `followText: "已关注"` → 已关注

#### 抖音 (Douyin)

```javascript
() => {
  const result = {};
  
  // 检查点赞按钮状态
  const likeBtn = document.querySelector('[data-e2e="video-player-digg"]');
  if (likeBtn) {
    result.likeCount = likeBtn.textContent?.trim();
    result.likeClasses = likeBtn.className?.includes && likeBtn.className.includes('active') ? 'active' : 'inactive';
  }
  
  // 检查收藏按钮状态
  const collectBtn = document.querySelector('[data-e2e="video-player-collect"]');
  if (collectBtn) {
    result.collectCount = collectBtn.textContent?.trim();
    result.collectClasses = collectBtn.className?.includes && collectBtn.className.includes('active') ? 'active' : 'inactive';
  }
  
  // 获取视频信息
  const title = document.querySelector('[class*="video-title"], [class*="title"]')?.textContent?.trim();
  const desc = document.querySelector('[class*="desc"], .chapter-content')?.textContent?.trim();
  result.title = title || desc || '';
  
  // 检查是否登录
  const avatar = document.querySelector('[class*="avatar"], img[alt*="头像"]');
  result.loggedIn = !!avatar;
  
  return result;
}
```

### 4.4 执行交互 — 仅执行 interactionActions 中列出的操作

#### 小红书 (XHS)：点赞/收藏（一个 JS 调用完成）

```javascript
async () => {
  const engageBar = document.querySelector('.engage-bar');
  if (!engageBar) return { error: 'no engage bar' };
  const result = {};
  
  const likeWrapper = engageBar.querySelector('.like-wrapper');
  if (likeWrapper) { likeWrapper.click(); result.likeClicked = true; }
  
  const collectWrapper = engageBar.querySelector('.collect-wrapper');
  if (collectWrapper) { collectWrapper.click(); result.collectClicked = true; }
  
  await new Promise(r => setTimeout(r, 800));
  
  const icons = [...engageBar.querySelectorAll('svg use')].map(u => u.getAttribute('href'));
  result.iconsAfter = icons;
  return result;
}
```

#### 抖音 (Douyin)：点赞/收藏

```javascript
async () => {
  const result = {};
  
  const likeBtn = document.querySelector('[data-e2e="video-player-digg"]');
  if (likeBtn) { likeBtn.click(); result.likeClicked = true; }
  else result.likeError = 'not found';
  
  await new Promise(r => setTimeout(r, 500));
  
  const collectBtn = document.querySelector('[data-e2e="video-player-collect"]');
  if (collectBtn) { collectBtn.click(); result.collectClicked = true; }
  else result.collectError = 'not found';
  
  await new Promise(r => setTimeout(r, 500));
  
  result.likeCount = document.querySelector('[data-e2e="video-player-digg"]')?.textContent?.trim();
  result.collectCount = document.querySelector('[data-e2e="video-player-collect"]')?.textContent?.trim();
  return result;
}
```

#### 关注（仅当 interactionActions 包含 follow 时执行）

⚠️ 关注操作风控风险较高，如果任务不需要 follow 则坚决不点。

- XHS: 用 `take_snapshot` 找到文本为"关注"的按钮，`click` 点击
- 抖音: 用 `take_snapshot` 找到 `uid` 为 "关注" button，`click` 点击

#### 评论（仅当 interactionActions 包含 comment 时执行）

**小红书 (XHS) 评论流程**：
1. 用 `take_snapshot` 找到评论输入框（"说点什么..." / "留下评论"）
2. `click` 点击输入框
3. `fill` 输入评论内容（或 `evaluate_script` 设置 textContent）
4. 用 `take_snapshot` 找到发送/发布按钮，`click` 发送
5. `wait` 1 秒等待评论发送

**抖音 (Douyin) 评论流程**：
1. 用 `take_snapshot` 找到评论 combobox（`placeholder="留下你的精彩评论吧"`）
2. `click` 点击 combobox 激活
3. `fill` 填入评论内容
4. `press_key` 按 `Enter` 发送评论

**评论生成规则**（适用于所有平台）：
- 根据阶段 4.2 获取的笔记/视频主题动态生成
- 10-25 字，表达赞赏或共鸣
- 加 1 个 emoji
- **绝不使用模板化、机械式语言**
- 避免与已有评论重复

## 阶段 5：截图

```
mcp__chrome-devtools__take_screenshot:
  filePath: "<TMPDIR>/task_screenshot.png"
```

**截图要求**：
- 截图中必须包含页面顶部用户名（用于平台结算查验）
- 截图中应可见已点赞/收藏的图标状态（红色/高亮/active class）
- 如果有评论，截图中应包含已发送的评论
- 保存为 `$TMPDIR/task_screenshot.png`

## 阶段 6：上传截图

截图上传必须在 `aitoearn.cn` 域名下执行（浏览器同源策略）。

**6.1 新建标签页导航到 aitoearn.cn：**

```
mcp__chrome-devtools__new_page:
  url: "https://aitoearn.cn/api/"
```

**6.2 注入上传逻辑（evaluate_script）：**

```javascript
() => {
  document.querySelectorAll('#task-upload').forEach(el => el.remove());
  const input = document.createElement('input');
  input.type = 'file';
  input.id = 'task-upload';
  input.style.cssText = 'position:fixed;top:10px;left:10px;z-index:99999';
  document.body.appendChild(input);
  
  const API_KEY = 'ak_4XHJXNoWCd51PWAW0orOD6lFl68IE2J5JPu55SM61RZklbGx';
  
  input.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    window.__taskUpload = { status: 'uploading' };
    try {
      // Step 1: 获取上传签名
      const signResp = await fetch('/api/assets/uploadSign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': API_KEY },
        body: JSON.stringify({ filename: `interaction_${Date.now()}.png`, size: file.size, type: 'userMedia' })
      });
      const signData = await signResp.json();
      if (signData.code !== 0) { window.__taskUpload = { status: 'error', step: 'sign', data: signData }; return; }
      
      // Step 2: PUT 直传到 OSS
      await fetch(signData.data.uploadUrl, { method: 'PUT', body: file, headers: { 'Content-Type': 'image/png' } });
      
      // Step 3: 确认上传
      const confirmResp = await fetch('/api/assets/' + signData.data.id + '/confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'x-api-key': API_KEY },
        body: JSON.stringify({ id: signData.data.id })
      });
      const confirmData = await confirmResp.json();
      window.__taskUpload = { status: 'done', url: confirmData.data?.url || signData.data.url };
    } catch(err) { window.__taskUpload = { status: 'error', message: err.message }; }
  });
  return { ready: true, origin: location.origin };
}
```

**6.3 上传截图文件：**

```
mcp__chrome-devtools__take_snapshot   // 找到 file input 的 uid
mcp__chrome-devtools__upload_file:
  filePath: "<TMPDIR>/task_screenshot.png"
  uid: "<file input uid>"
```

**6.4 获取上传结果：**

轮询 `evaluate_script` 执行 `() => window.__taskUpload` 直到 `status !== 'uploading'`，提取 `url`。

## 阶段 7：提交任务

**互动任务用 submitInteractionTask：**

```
mcp__aitoearn__submitInteractionTask:
  userTaskId: "<userTaskId>"
  screenshotUrls: ["<上传后的URL>"]
```

---

## 平台差异速查

| 特性 | 小红书 (XHS) | 抖音 (Douyin) |
|------|-------------|--------------|
| 点赞选择器 | `.engage-bar .like-wrapper` | `[data-e2e="video-player-digg"]` |
| 收藏选择器 | `.engage-bar .collect-wrapper` | `[data-e2e="video-player-collect"]` |
| 状态检测 | SVG `use href` (#like/#liked) | CSS class 含 `active` |
| 评论输入 | 点击 textarea → type → 点发送 | fill combobox → Enter |
| 评论 placeholder | "说点什么..." | "留下你的精彩评论吧" |
| 评论输入类型 | textarea / contenteditable | combobox (role="combobox") |
| 评论发送方式 | 找到发送按钮 click | press_key Enter |
| 导航链接 | `xhslink.com` → `xiaohongshu.com/explore/` | `v.douyin.com` → `douyin.com/video/` |
| 登录检测 | 页面含用户名/头像 | 页面含头像图片 |

---

## 错误处理

| 错误 | 原因 | 处理方式 |
|------|------|---------|
| 需要登录 | 未登录 | 提示用户在 Chrome 中登录对应平台，然后继续 |
| `fansNum` 不满足 | 账号粉丝数不足 | 跳过该任务，尝试下一个 |
| Task status invalid | 任务已被接受或状态异常 | 检查 `listMyUserTasks`，避免重复接单 |
| 401 Unauthorized 上传 | API Key 错误 | 检查 API Key 是否正确 |
| CORS 上传失败 | 不在 aitoearn.cn 域名 | 确保在 `aitoearn.cn` 域名下执行上传 |
| 图标已为 #liked/#collected | 已交互过 | 跳过该操作，直接进行下一步 |
| 已关注 | 已关注过 | 跳过关注操作 |
| `INTERACTION_SCREENSHOT_CANNOT_ANALYZE` | 平台 AI 校验模型异常 | 非截图质量问题，告知用户等待平台修复或人工审核 |
| 无可用任务 | 所有任务粉丝数不足/已接 | 告知用户具体原因，建议等待新任务发布 |
| Douyin combobox fill 无效 | 输入框类型特殊 | 改用 `click` 激活 → `evaluate_script` 设置 value → `press_key` Enter |

---

## 并发与效率

- 阶段 0（检查已接任务 + 获取粉丝数）可并行执行
- 接受任务后，导航和获取任务详情可并行
- 点赞和收藏可一次 JS 调用完成
- 评论发送后立即开始截图（不等评论刷新）
- 上传和提交串行依赖，必须按序执行

---

## 评论生成策略

根据笔记/视频主题动态生成：

| 主题类型 | 示例 |
|---------|------|
| **美食/旅游** | "看着太诱人了！收藏了周末去打卡 😋" |
| **美妆/穿搭** | "这个配色也太温柔了吧，被种草了 ✨" |
| **知识/干货** | "干货满满！学到了，感谢分享 👍" |
| **生活/日常** | "同款生活！太真实了哈哈 😂" |
| **亲子/遛娃** | "以蔬换书真有创意，下次带娃来体验 📚" |
| **手工/非遗** | "非遗手艺太美了，感受到了匠人温度 🧶" |
| **通用** | "好棒的内容，先收藏了慢慢看 ❤️" |

**绝对避免**：
- 模板化回复（"感谢分享" / "很棒的帖子"）
- 与现有评论重复（先读一下已有评论再写）
- 过于营销化的语言
- 超过 30 字的冗长评论
- 无 emoji 的干巴巴评论

---

# 二、CPE 推广任务流程 (`type: "promotion"`)

⚠️ **仅限 XHS 平台**，且需要在 aitoearn.cn 使用 Chrome 自动化点击发布按钮。

CPE 任务的特点是：平台已准备好所有素材（图片、标题、描述、话题），用户只需在 AiToEarn 网站上点击"发布"按钮，平台通过 `publishingChannel: "internal"` 自动发布到小红书。

### 阶段 P1：接受任务

```
mcp__aitoearn__listTaskMarket:
  platform: "xhs"
  type: "promotion"
  pageSize: 10
```

筛选：
- `currentRecruits < maxRecruits`（还有名额）
- `cpeReward > 0`（CPE 计费）

```
mcp__aitoearn__acceptTask:
  taskId: "<选中的任务ID>"
```

记录返回的 `userTaskId`。

### 阶段 P2：获取任务详情

```
mcp__aitoearn__getMyUserTaskDetail:
  userTaskId: "<userTaskId>"
```

确认返回数据中有 `materialId` 和 `publishRecordId`。

### 阶段 P3：在 aitoearn.cn 上点击发布

**核心思路**：不需要操作 xiaohongshu.com，不需要上传素材。一切都在 AiToEarn 平台上完成。平台内部系统会自动发布到小红书。

**P3.1 确保已登录 aitoearn.cn：**

```
mcp__chrome-devtools__navigate_page:
  type: "url"
  url: "https://aitoearn.cn"
```

如果页面跳转到登录页，提示用户在 Chrome 中登录。

**P3.2 导航到任务对话页：**

```
mcp__chrome-devtools__navigate_page:
  type: "url"
  url: "https://aitoearn.cn/chat/<taskId>"
```

这会打开该任务的对话页面，平台可能自动弹出 PublishDialog（含预填充的素材、标题、描述）。

**P3.3 查找并点击发布按钮：**

用 `take_snapshot` 查看页面结构，找到以下任一元素：
- "发布" 按钮
- "确认发布" 按钮
- PublishDialog 弹窗中的发布按钮

用 `click` 点击发布按钮。

**P3.4 等待发布完成：**

```
mcp__aitoearn__getPublishingTaskStatus:
  flowId: "<flowId>"
```

轮询直到状态变为 `published`。

### 阶段 P4：确认提交

CPE 任务通过 AiToEarn 内部发布后，平台会自动创建 `publishRecord` 并触发审核。通常无需手动调用 `submitTask`。

用 `getMyUserTaskDetail` 确认任务状态已更新。

---

# 三、已知限制

1. **CPE 发布流程需实际验证**：第二部分（P3）的 aitoearn.cn 发布按钮定位需要实际跑一次来确认具体的 DOM 结构和交互流程。
2. **粉丝数门槛**：低粉丝数账号能接的互动任务有限。建议用户先养号涨粉。
3. **平台 AI 校验**：`INTERACTION_SCREENSHOT_CANNOT_ANALYZE` 是平台侧 AI 模型问题，非 skill 或截图质量问题。
4. **TikTok 任务**：当前市场无 TikTok 任务。
5. **抖音 follow 风险**：抖音关注操作风控严格，优先选择不含 follow 的任务。
6. **XHS 发布无 MCP 工具**：MCP 没有 `publishPostToXhs`，CPE 任务必须通过 aitoearn.cn Web UI 完成。
