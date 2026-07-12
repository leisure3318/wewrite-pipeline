# wewrite-pipeline

全流程公众号发布助手——从视频字幕 / 本地文稿 / 网页 URL 到微信草稿箱，串联写作、标题优化、图片提示词、自动生图、排版和发布。

## 它做什么

```
[你的终端 / Agent]                         [Claude Code / Codex]
YouTube 字幕 / 本地文稿 / Web URL → 写作 → 标题候选 → 提示词生成 → 可配置图片 API 生图 → 格式化 → HTML → 草稿箱
```

串联的技能链：
- **wewrite** — 框架选择、persona / 范文 / playbook 注入、分段自检、写作、SEO 验证
- **baoyu-url-to-markdown** — 普通网页 URL 抓取为干净 Markdown（非 YouTube URL）
- **baoyu-format-markdown/title-formulas** — 生成 5 个标题候选并默认选最强标题
- **baoyu-cover-image** — 封面提示词（5 维度）
- **baoyu-article-illustrator** — 配图提示词
- **OpenAI 兼容图片 API** — 自动生成封面和正文配图，可接入你自己的服务商
- **baoyu-format-markdown** — Markdown 排版和标题优化
- **baoyu-markdown-to-html** — 渲染为微信兼容 HTML
- **baoyu-post-to-wechat** — 上传图片并推送草稿箱

每篇文章独立隔离到 `~/wewrite-articles/YYYY-MM-DD-{slug}/`，随时可以中断恢复。

---

## 前置条件

### 必须安装

| 依赖 | 作用 | 检查 | 安装 |
|------|------|------|------|
| Claude Code / Codex | 运行 skill 的宿主环境 | `claude --version` 或 Codex App | [Claude Code](https://claude.ai/code) |
| Node.js 18+ | 发布脚本运行时（npx tsx） | `node --version` | `brew install node` |
| wewrite skill | 写作核心 | `find ~/.agents/skills ~/.codex/skills ~/.claude/skills -path "*/wewrite/SKILL.md" 2>/dev/null` | 见下方 |
| baoyu-skills 插件 | 网页抓取、封面/配图/排版/发布 | `find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "wechat-api.ts" 2>/dev/null \| head -1` | 见下方 |

**一键检查所有前置条件**：

```bash
echo "=== 检查 wewrite-pipeline 前置条件 ===" && \
echo -n "Claude Code:    " && (claude --version 2>/dev/null | head -1 || echo "❌ 未安装") && \
echo -n "Node.js:        " && (node --version 2>/dev/null || echo "❌ 未安装") && \
echo -n "npx:            " && (npx --version 2>/dev/null || echo "❌ 未安装") && \
echo -n "python3:        " && (python3 --version 2>/dev/null || echo "❌ 未安装") && \
echo -n "PyYAML:         " && (python3 -c "import yaml; print('ok')" 2>/dev/null || echo "⚠️  pip install pyyaml") && \
echo -n "wewrite skill:  " && (find ~/.agents/skills ~/.codex/skills ~/.claude/skills -path "*/wewrite/SKILL.md" 2>/dev/null | head -1 | grep -q . && echo "ok" || echo "❌ 未安装") && \
echo -n "baoyu-skills:   " && (find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "wechat-api.ts" 2>/dev/null | head -1 | grep -q . && echo "ok" || echo "❌ 未安装") && \
echo -n "微信凭证:       " && (grep -q WECHAT_APP_ID ~/.baoyu-skills/.env 2>/dev/null && echo "ok" || echo "⚠️  需要配置（见步骤 3）")
```

#### 安装 wewrite skill

```bash
mkdir -p ~/.agents/skills
cd ~/.agents/skills
git clone https://github.com/oaker-io/wewrite.git wewrite
```

#### 安装 baoyu-skills 插件

在 Claude Code 中运行：
```
/install baoyu-skills
```
或参考 [baoyu-skills 文档](https://github.com/JimLiu/baoyu-skills)。

### 可选（YouTube 字幕下载）

| 工具 | 作用 | 安装 |
|------|------|------|
| yt-dlp | 下载 YouTube 字幕文件 | `brew install yt-dlp` |
| markitdown | VTT 字幕转 Markdown | `pip install markitdown` |

---

## 安装 wewrite-pipeline

### 方式一：symlink（推荐，方便 git pull 更新）

```bash
git clone https://github.com/yourname/wewrite-pipeline.git ~/Code/wewrite-pipeline
ln -s ~/Code/wewrite-pipeline ~/.agents/skills/wewrite-pipeline
```

### 方式二：直接复制

```bash
git clone https://github.com/yourname/wewrite-pipeline.git ~/.agents/skills/wewrite-pipeline
```

### 验证安装

新开一个 Claude Code 对话，运行：

```
/wewrite-pipeline --help
```

或直接查看 skill 是否出现在列表中：

```
/skills
```

看到 `wewrite-pipeline` 就说明安装成功。

---

## 配置

### 1. 微信 API 凭证（必须，仅需配置一次）

先运行一次 `/baoyu-post-to-wechat`，它会引导你完成配置，生成：

```
~/.baoyu-skills/.env
```

内容格式：
```
WECHAT_APP_ID=wx...
WECHAT_APP_SECRET=...
```

wewrite-pipeline 直接复用这份配置，不需要额外设置。

### 2. 图片 API 凭证（自动生图需要）

将你的图片服务商配置写入 `.env`。接口需要兼容 OpenAI 的
`POST /images/generations`；不同服务商的地址、模型和尺寸支持范围请以其文档为准：

```bash
IMAGE_API_KEY=...
IMAGE_API_BASE=https://your-image-api.example/v1
IMAGE_MODEL=your-image-model
```

pipeline 会自动读取：

- 当前工作目录 `.env`
- `$XDG_CONFIG_HOME/baoyu-skills/.env` 或 `~/.config/baoyu-skills/.env`
- `~/.baoyu-skills/.env`

可选配置：

```bash
IMAGE_API_BACKEND=my-provider  # 写入 meta.yaml 的服务商标识，可不填
COVER_IMAGE_SIZE=1808x768
ARTICLE_IMAGE_SIZE=1536x864
```

如果只需要重生成封面：

```bash
python3 scripts/generate-images.py ~/wewrite-articles/2026-05-01-my-topic --cover-only --force
```

### 3. 第三方图片 API prompt 授权（可选）

Step 3 会把封面和正文配图 prompt 发送到你配置的第三方图片 API。默认每篇文章需要明确授权；如果你希望普通公众号文章自动生图，可以创建：

```yaml
# ~/.baoyu-skills/wewrite-pipeline/EXTEND.md
image_prompt_auto_consent: true
```

旧配置 `myweb3_prompt_auto_consent: true` 也继续有效，方便已有本地环境无缝升级。这个长期授权不覆盖密钥、客户资料、私密聊天、未公开商业资料等敏感素材；遇到这类内容 pipeline 仍应暂停确认。

### 4. `yt-article` 函数（仅 YouTube 来源时需要）

在 `~/.zshrc` 末尾添加：

```bash
function yt-article() {
  local url=$1
  local slug=${2:-$(date +%Y-%m-%d)}
  local outdir="$HOME/wewrite-articles/$slug/00-source"
  mkdir -p "$outdir"
  yt-dlp \
    --cookies "$HOME/.yt-cookies.txt" \
    --write-auto-sub --sub-lang en \
    --skip-download --no-playlist \
    --output "$outdir/%(title)s.%(ext)s" \
    "$url"
  for f in "$outdir"/*.vtt; do
    [ -f "$f" ] && markitdown "$f" -o "${f%.vtt}.md"
  done
  echo "✓ 字幕已保存到 $outdir"
}
```

```bash
source ~/.zshrc
```

### 5. YouTube Cookie（仅 YouTube 来源时需要，有效期约 2-4 周）

1. 安装 Chrome 插件「Get cookies.txt LOCALLY」
2. 登录 YouTube，用插件导出 cookies
3. 保存到 `~/.yt-cookies.txt`

过期标志：运行 `yt-article` 时报 "Sign in" 错误 → 重新导出 cookie 覆盖即可。

---

## 使用

### 从本地字幕文件开始

```bash
# 在 Claude Code 中
/wewrite-pipeline ~/Downloads/transcript.md my-article-slug
```

### 从 YouTube 视频开始

**第一步（你的终端，约 10 秒）**：
```bash
yt-article "https://youtube.com/watch?v=6MBq1paspVU" "2026-04-28-Obsidian-ClaudeCode"
```

**第二步（Claude Code）**：
```bash
/wewrite-pipeline ~/wewrite-articles/2026-04-28-Obsidian-ClaudeCode
# 或直接传 YouTube URL，pipeline 会告诉你运行命令
/wewrite-pipeline "https://youtube.com/watch?v=xxx" "2026-05-ai-features"
```

### 从网页 URL 开始

普通网页 URL 不需要先手动下载。pipeline 会优先使用 `baoyu-url-to-markdown` 的 `baoyu-fetch`，失败时降级到当前 agent 的网页抓取能力，并把正文保存为 `00-source/transcript.md`。

```bash
/wewrite-pipeline "https://example.com/blog/post" web-article-topic
```

### 中断后恢复

```bash
/wewrite-pipeline ~/wewrite-articles/2026-05-01-my-article
```

pipeline 读取 `meta.yaml` 中的 `status`，从上次停止的地方继续。

---

## 流程详解

```
Step 0  初始化目录           ~/wewrite-articles/YYYY-MM-DD-slug/ 建立完整结构
Step 1  wewrite 写作         transcript → 原稿 draft.md（加载最新 persona/playbook/范文/实时自检规则）
Step 1.6 标题候选            读取 title-formulas.md，生成 5 个候选并写回最强标题
Step 2  图片提示词           封面 → 02-cover/prompts/，配图 → 03-images/prompts/
Step 3  自动生成图片         已配置的图片 API 生成 cover.png 和正文配图
Step 4  格式化 + 插图        插入图片引用，baoyu-format-markdown 优化排版
Step 5  转 HTML             baoyu-markdown-to-html 渲染
Step 6  发布草稿箱           npx tsx wechat-api.ts 推送，输出 media_id
```

**关于 WeWrite 同步**：

Step 1 不复制一份固定的旧写作规则，而是在每次运行时读取当前安装的 `wewrite` skill：`writing-guide.md`、`playbook.md`、`history.yaml`、`style.yaml`、persona、范文库/种子段落，以及新版的 `persona-selection.md`、`realtime-check.md`、`commands.md`（存在时）。pipeline 额外强制：公开正文必须是独立公众号文章，要有明确作者观点，末尾要有可复述总结，并在发布前执行 humanness / 平台硬限制检查。

**关于图片生成**：

pipeline 生成 Baoyu prompt 后，会调用 `scripts/generate-images.py` 自动生成图片。脚本默认跳过已存在图片，避免覆盖人工修过的图；需要重生成时显式加 `--force`。旧的 `generate-images-myweb3.py` 命令仍可继续使用。

常用恢复命令：

```bash
# 只重生成封面
python3 scripts/generate-images.py ~/wewrite-articles/2026-05-01-my-topic --cover-only --force

# 只重生成正文配图
python3 scripts/generate-images.py ~/wewrite-articles/2026-05-01-my-topic --body-only --force

# 校验 Baoyu prompt 结构
python3 scripts/validate-image-prompts.py ~/wewrite-articles/2026-05-01-my-topic
```

---

## 文章目录结构

```
~/wewrite-articles/
└── 2026-05-01-my-topic/
    ├── meta.yaml              ← 流程状态，随时可查
    ├── 00-source/
    │   └── transcript.md      ← 原始字幕（markitdown 转换后）
    ├── 01-article/
    │   ├── draft.md           ← wewrite 原稿
    │   ├── draft-formatted.md ← 格式化后
    │   └── draft-formatted.html
    ├── 02-cover/
    │   ├── prompts/
    │   │   └── 01-cover-my-topic.md
    │   └── cover.png          ← 已配置图片 API 自动生成
    └── 03-images/
        ├── outline.md
        ├── prompts/
        │   ├── 01-infographic-concept.md
        │   └── 02-scene-example.md
        └── 01-infographic-concept.png    ← 已配置图片 API 自动生成
```

`meta.yaml` 示例：
```yaml
slug: my-topic
date: "2026-05-01"
source: ~/Downloads/transcript.md
status: published          # init / drafted / prompts_ready / images_ready / formatted / html_ready / published
title: "文章标题"
summary: "一句话摘要"
media_id: abc123xyz
published_at: "2026-05-01T14:30:00+08:00"
```

---

## 已知限制

| 限制 | 原因 | 计划 |
|------|------|------|
| 图片 API 可能返回 413 | prompt 或请求体过大 | 精简 prompt / 降低图片数量 / 使用本地兼容代理 |
| YouTube 字幕需在用户终端下载 | Claude Code 沙箱 IP 被 YouTube 封锁 | 有官方 YouTube Data API key 后可解决 |
| bun 不能发布 | 系统防火墙拦截 bun 进程外网 | 已改用 npx tsx；或给 bun 开放防火墙 |

---

## 故障排查

**找不到 wechat-api.ts**
```bash
find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "wechat-api.ts"
```
空结果 → baoyu-skills 插件未安装或路径变了。

**meta_id 提取失败**
手动查看 npx tsx 的输出，找 `"media_id"` 行，手动更新 `meta.yaml`。

**wewrite 输出文件找不到**
手动把 `~/.agents/skills/wewrite/output/`、`~/.codex/skills/wewrite/output/` 或 `~/.claude/skills/wewrite/output/` 里最新的 `.md` 复制到
`~/wewrite-articles/{slug}/01-article/draft.md`，然后恢复 pipeline。

**图片相对路径在 HTML 中失效**
确保配图文件名和 `outline.md` 里的 Filename 字段一致。

**图片 prompt 校验失败**
运行：

```bash
python3 scripts/validate-image-prompts.py ~/wewrite-articles/{slug}
```

如果缺少 `ZONES` / `LABELS` / `COLORS` / `STYLE` / `ASPECT`，回到 baoyu-article-illustrator 模板重建 prompt，不要用简化自然语言 prompt 顶上。

**标题没有被自动优化**
确认本地能找到：

```bash
find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -path "*/baoyu-format-markdown/references/title-formulas.md"
```

找不到时先安装或更新 baoyu-format-markdown。

---

## 分享给其他用户

skill 没有任何硬编码路径，可以直接分享使用。对方按「前置条件 → 安装 → 配置」章节操作即可，不需要修改任何代码。

---

## 版权

MIT License. 基于 [wewrite](https://github.com/oaker-io/wewrite) 和 [baoyu-skills](https://github.com/JimLiu/baoyu-skills)。
