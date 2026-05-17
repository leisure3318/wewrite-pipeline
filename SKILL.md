---
name: wewrite-pipeline
description: |
  公众号内容全流程 pipeline：视频字幕 / 本地文稿 → 微信草稿箱。
  自动初始化每篇文章的隔离目录结构，串联 wewrite（写作）+
  baoyu-cover-image（封面提示词）+ baoyu-article-illustrator（配图提示词）+
  baoyu-format-markdown（格式化）+ baoyu-markdown-to-html（排版）+
  baoyu-post-to-wechat（发布），并通过 myweb3 自动生成封面和正文配图。
  触发词：wewrite-pipeline、全流程、pipeline、一键发布、字幕转公众号
user_invocable: true
---

# WeWrite Pipeline — 公众号全流程编排

## 概述

将「有原始素材」到「草稿箱」之间所有重复步骤自动化。图片提示词仍由 Baoyu 原始模板生成，随后通过 myweb3 兼容的图片 API 自动生成封面和正文配图。

### 文章目录结构（每篇独立隔离）

```
~/wewrite-articles/
└── YYYY-MM-DD-{slug}/
    ├── 00-source/
    │   └── transcript.md        # 输入字幕 / 文稿（UTF-8 纯文本）
    ├── 01-article/
    │   ├── draft.md             # wewrite 生成的原稿
    │   ├── draft-formatted.md   # 格式化后（含图片引用）
    │   └── draft-formatted.html # 最终 HTML（用于发布）
    ├── 02-cover/
    │   ├── prompts/
    │   │   └── 01-cover-{slug}.md   # 封面提示词
    │   └── cover.png            # myweb3 自动生成
    ├── 03-images/
    │   ├── outline.md           # 配图规划
    │   ├── prompts/
    │   │   ├── 01-{type}-{slug}.md
    │   │   └── ...              # 各张配图提示词
    │   └── *.png                # myweb3 自动生成
    └── meta.yaml                # 文章元数据和流程状态
```

---

## 行为声明

- **默认全自动**：Step 0 → Step 6 连续运行；YouTube 字幕下载和缺少必要 API 凭证除外。
- **自动图片生成**：Step 3 读取 Step 2 产出的 Baoyu prompt 文件，通过 myweb3 `/images/generations` 自动生成图片。
- **图片提示词硬约束**：Step 2 必须使用 baoyu-cover-image / baoyu-article-illustrator 的原始 skill 模板生成或重建提示词；禁止用临时手写、口述简化版、自由发挥版替代 baoyu 模板。
- **图片 API 配置**：Step 3 读取 `IMAGE_API_KEY` 或 `MYWEB3_API_KEY`；可选 `IMAGE_API_BASE`（默认 `https://api.myweb3.cc/v1`）、`IMAGE_MODEL`（默认 `gpt-image-2`）、`COVER_IMAGE_SIZE`（默认 `1808x768`）、`ARTICLE_IMAGE_SIZE`（默认 `1536x864`）。尺寸会向上取整为 16 的倍数。
- **网络限制规避**：发布步骤强制使用 `npx --yes tsx` 调用 `wechat-api.ts`，禁止使用 `bun`（bun 出口网络在本环境被系统拦截）。
- **内容来源隐身硬约束**：YouTube / 字幕 / 访谈 / 文稿只能作为素材来源。除非用户明确要求写观后感、解读、逐字稿或来源评述，公开正文必须写成独立公众号文章，禁止用“看完这个视频 / 视频作者说 / 视频里 / 字幕里 / 作者说”等来源框架。
- **路径约定**：本文档中 `{ARTICLE_DIR}` 指当次运行的文章根目录，`{skill_dir}` 指本 SKILL.md 所在目录。
- **进度追踪**：在 Codex 中优先用 `update_plan` 创建/更新步骤；不可用时用简短进度列表，完成一步标记一步。

---

## 调用格式

```
$wewrite-pipeline <素材> [slug]
# 或直接用自然语言：把 <素材> 跑完整公众号 pipeline
```

| 参数 | 说明 |
|------|------|
| `<素材>` | 本地 `.md` / `.vtt` 文件路径，或 YouTube URL |
| `[slug]` | 可选，英文 kebab-case（2-4 词）。不传则从内容自动推断 |

**示例**：
```bash
$wewrite-pipeline ~/Downloads/video-transcript.md claude-regression-2026
$wewrite-pipeline "https://youtube.com/watch?v=xxx" ai-new-features
$wewrite-pipeline ~/wewrite-articles/2026-05-01-my-topic   # 恢复模式
```

---

## 主管道

### 启动时创建任务

```
Plan item: "Step 0: 初始化目录"
Plan item: "Step 1: wewrite 写作"
Plan item: "Step 2: 生成图片提示词"
Plan item: "Step 3: 自动生成图片（myweb3）"
Plan item: "Step 4: 格式化 + 插图"
Plan item: "Step 5: 转换 HTML"
Plan item: "Step 6: 发布草稿箱"
```

---

### Step 0: 初始化目录

**进度：Step 0 -> in_progress**

**0.1 输入类型检测**：

| 输入 | 检测规则 | 处理 |
|------|---------|------|
| 本地 `.md` 文件 | `test -f <path>` 且以 `.md` 结尾 | 复制到 `00-source/transcript.md` |
| 本地 `.vtt` 文件 | `test -f <path>` 且以 `.vtt` 结尾 | 尝试 markitdown 转换，失败则直接复制 |
| YouTube URL | 匹配 `https?://(www\.)?youtu(be\.com|\.be)/` | 输出 yt-article 命令，等待用户 |
| 已有文章目录 | `test -d <path>/00-source` | 进入恢复模式（见文末）|

**0.2 YouTube 暂停提示**（仅 URL 输入时）：

```
检测到 YouTube URL，字幕需在你的终端下载（沙箱网络限制）。

请运行（约 10 秒）：

  yt-article "<YouTube URL>" "<slug>"

完成后字幕保存到 ~/wewrite-articles/<slug>/00-source/，
告诉我「字幕已就绪」或直接把路径发过来，pipeline 继续。

没有 yt-article 命令？在 ~/.zshrc 加入（见 README.md 的安装说明）。
```

**0.3 创建目录结构**：

```bash
DATE=$(date +%Y-%m-%d)
ARTICLE_DIR="$HOME/wewrite-articles/${DATE}-{slug}"

# 如果目录已存在，询问是否继续
if [ -d "$ARTICLE_DIR" ]; then
  # 提示用户：目录已存在，是否覆盖还是选新 slug？
fi

mkdir -p "$ARTICLE_DIR/00-source"
mkdir -p "$ARTICLE_DIR/01-article"
mkdir -p "$ARTICLE_DIR/02-cover/prompts"
mkdir -p "$ARTICLE_DIR/03-images/prompts"
```

**0.4 复制 transcript**：

```bash
# .md 直接复制
cp "{input}" "$ARTICLE_DIR/00-source/transcript.md"

# .vtt 先尝试 markitdown 转换
if command -v markitdown &>/dev/null; then
  markitdown "{input}" -o "$ARTICLE_DIR/00-source/transcript.md"
else
  cp "{input}" "$ARTICLE_DIR/00-source/transcript.md"
fi
```

**0.5 写入 meta.yaml**：

```yaml
slug: "{slug}"
date: "{YYYY-MM-DD}"
source: "{原始输入路径或URL}"
status: "init"
title: null
summary: null
media_id: null
published_at: null
errors: []
```

告知用户：`✓ 文章目录已初始化：{ARTICLE_DIR}`

**进度：Step 0 -> completed**

---

### Step 1: 生成文章

**进度：Step 1 -> in_progress**

读取 `{ARTICLE_DIR}/00-source/transcript.md` 的内容，调用 **wewrite skill** 进行写作。

**调用 wewrite 时的指令**：

> 这是一篇视频字幕 / 文稿内容，已有明确选题和素材。
> 请跳过选题和热点抓取（Step 2），直接从框架选择（Step 3）开始，
> 把这份素材当作内容基础，完成写作和质量验证流程。
> **公开正文必须是独立公众号文章**：素材来源可以保留在 frontmatter / meta.yaml，正文不得写成“看完视频后的感想”、不得出现“视频作者说 / 视频里 / 字幕里 / 这个视频”等来源框架；除非用户明确要求观后感或来源评述。
> **输出文件保存到 `{ARTICLE_DIR}/01-article/draft.md`**，
> 而不是 wewrite 的默认 output 目录。

wewrite 完成后，确认 `{ARTICLE_DIR}/01-article/draft.md` 存在。
如果 wewrite 仍写入了默认目录，用以下命令找到并复制：

```bash
# 找到 wewrite 最新生成的 md 文件（排除 -formatted 后缀）
LATEST=$(find ~/.agents/skills/wewrite/output ~/.claude/skills/wewrite/output -name "*.md" \
  -not -name "*-formatted*" -newer "$ARTICLE_DIR/00-source/transcript.md" \
  2>/dev/null | sort | tail -1)

[ -n "$LATEST" ] && cp "$LATEST" "$ARTICLE_DIR/01-article/draft.md"
```

**Step 1.5: 独立文章来源框架校验**：

在进入图片提示词、格式化、HTML 和发布前，必须验证公开正文没有把素材来源暴露成叙事框架：

```bash
python3 "{skill_dir}/scripts/validate-standalone-article.py" "$ARTICLE_DIR/01-article/draft.md"
```

如果校验失败，必须先重写 `draft.md`，让文章以独立观点 / 方法 / 清单呈现；不要继续 Step 2，也不要发布。允许在 frontmatter / meta.yaml 保留 source URL 作为内部追踪信息。

**更新 meta.yaml**：从 draft.md frontmatter 提取 title / summary：

```bash
# 用 Python 提取 YAML frontmatter
python3 - "$ARTICLE_DIR/01-article/draft.md" "$ARTICLE_DIR/meta.yaml" <<'EOF'
import sys, re
draft_path, meta_path = sys.argv[1], sys.argv[2]
content = open(draft_path).read()
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if m:
    import yaml
    fm = yaml.safe_load(m.group(1))
    meta = yaml.safe_load(open(meta_path).read()) or {}
    meta['title'] = fm.get('title') or meta.get('title')
    meta['summary'] = fm.get('summary') or fm.get('description') or meta.get('summary')
    meta['status'] = 'drafted'
    open(meta_path, 'w').write(yaml.dump(meta, allow_unicode=True, default_flow_style=False))
EOF
```

**进度：Step 1 -> completed**

---

### Step 2: 生成图片提示词

**进度：Step 2 -> in_progress**

> 本步骤只生成提示词文件，不调用任何图片生成 API。图片生成统一交给 Step 3 的 myweb3 自动化脚本。

**强制模板规则（不可跳过）**：

- 必须先定位并读取真实 baoyu skill 文档，至少包括：
  - `baoyu-cover-image/SKILL.md`
  - `baoyu-cover-image/references/workflow/prompt-template.md`
  - `baoyu-article-illustrator/SKILL.md`
  - `baoyu-article-illustrator/references/workflow.md`
  - `baoyu-article-illustrator/references/prompt-construction.md`
- 封面提示词必须符合 `baoyu-cover-image` 的 prompt template：YAML frontmatter + `# Content Context`、`# Visual Design`、`# Text Elements`、`# Mood Application`、`# Font Application`、`# Composition`。
- 正文配图提示词必须符合 `baoyu-article-illustrator` 的 prompt construction：YAML frontmatter + type-specific template，并包含 `ZONES` / `LABELS` / `COLORS` / `STYLE` / `ASPECT` 等结构化段落。
- 允许根据文章内容填充模板字段；不允许把模板压缩成几段自然语言描述，不允许只写“请生成一张图”的简化 prompt。
- 如果当前运行环境不能直接调用 baoyu skill，也必须按上述 baoyu 原始模板重建完整 prompt；重建前仍要读取对应模板文档。

**2.1 定位 baoyu-cover-image skill**：

```bash
COVER_SKILL=$(find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "SKILL.md" \
  -path "*/baoyu-cover-image/*" 2>/dev/null | head -1 | xargs dirname)
```

**2.2 调用 baoyu-cover-image**（仅生成提示词）：

调用 baoyu-cover-image skill，传入 `{ARTICLE_DIR}/01-article/draft.md`，
使用 `--quick` 跳过维度确认，明确指定输出目录为 `{ARTICLE_DIR}/02-cover/`，
并**在所有图片生成步骤前停止**（不调用任何 image backend）。

提示词文件生成后，确保它在 `{ARTICLE_DIR}/02-cover/prompts/` 下。
如果 skill 把文件写到了其他位置，执行移动：

```bash
# 找到封面提示词并移动
find "$COVER_SKILL" -name "*.md" -path "*/prompts/*" -newer \
  "$ARTICLE_DIR/01-article/draft.md" 2>/dev/null | while read f; do
  cp "$f" "$ARTICLE_DIR/02-cover/prompts/$(basename "$f")"
done

# 也检查 cover-image/{slug}/ 目录（baoyu 默认 independent 模式）
find . -maxdepth 4 -name "*.md" -path "*/cover-image/*/prompts/*" \
  -newer "$ARTICLE_DIR/01-article/draft.md" 2>/dev/null | while read f; do
  cp "$f" "$ARTICLE_DIR/02-cover/prompts/$(basename "$f")"
done
```

封面提示词验收门槛：

```bash
rg -n "^---|^type: cover|^palette:|^rendering:|^# Content Context|^# Visual Design|^# Text Elements|^# Mood Application|^# Font Application|^# Composition" \
  "$ARTICLE_DIR/02-cover/prompts"
```

若缺少上述结构，视为生成失败；必须回到 baoyu-cover-image 模板重新生成/重建，不能用手写简化版补齐。

**2.3 调用 baoyu-article-illustrator**（仅生成提示词）：

调用 baoyu-article-illustrator skill，传入 `{ARTICLE_DIR}/01-article/draft.md`，
density = balanced（3-5 张），`--quick`，
输出 outline.md 和提示词到 `{ARTICLE_DIR}/03-images/`，
同样在图片生成步骤前停止。

确保文件位置正确：

```bash
# 若 illustrator 默认写到 draft 同级的 imgs/ 子目录
SRC_IMGS="$ARTICLE_DIR/01-article/imgs"
if [ -d "$SRC_IMGS" ]; then
  cp -r "$SRC_IMGS/outline.md" "$ARTICLE_DIR/03-images/" 2>/dev/null
  cp -r "$SRC_IMGS/prompts/"* "$ARTICLE_DIR/03-images/prompts/" 2>/dev/null
fi
```

正文配图提示词验收门槛：

```bash
rg -n "^---|^illustration_id:|^type:|^style:|^palette:|^ZONES:|^LABELS:|^COLORS:|^STYLE:|^ASPECT:" \
  "$ARTICLE_DIR/03-images/prompts"
```

若任一提示词缺少 YAML frontmatter 或缺少 type-specific 结构段落，视为生成失败；必须回到 baoyu-article-illustrator 模板重新生成/重建，不能用手写简化版补齐。

**更新 meta.yaml** `status: "prompts_ready"`

**进度：Step 2 -> completed**

---

### Step 3: 自动生成图片（myweb3）

**进度：Step 3 -> in_progress**

读取 Step 2 生成的 Baoyu prompt 文件，调用 myweb3 兼容图片 API 自动生成图片：

- 封面：读取 `{ARTICLE_DIR}/02-cover/prompts/*.md` 的第一份 prompt，生成 `{ARTICLE_DIR}/02-cover/cover.png`
- 正文配图：读取 `{ARTICLE_DIR}/03-images/prompts/*.md`，按文件名排序，生成 `{ARTICLE_DIR}/03-images/{prompt_stem}.png`
- 如果同名 `.png/.jpg/.jpeg/.webp` 已存在，默认跳过，避免覆盖手动修过的旧图；需要重生成时显式加 `--force`
- API 响应优先读取 `data[0].b64_json` 并保存为 PNG；如果返回 `url`，下载对应图片
- 请求超时时间 300 秒；只对 timeout 和 `500/502/503/504/524` 这类临时错误重试，重试间隔为 10 秒、20 秒

**3.1 环境变量要求**：

```bash
# 必填二选一
export IMAGE_API_KEY="..."
# 或
export MYWEB3_API_KEY="..."

# 可选
export IMAGE_API_BASE="https://api.myweb3.cc/v1"
export IMAGE_MODEL="gpt-image-2"
export COVER_IMAGE_SIZE="1808x768"
export ARTICLE_IMAGE_SIZE="1536x864"
```

本地服务 / 服务器环境如果已有 myweb3 代理，优先使用：

```bash
export IMAGE_API_BASE="http://host.docker.internal:8317/v1"
```

**3.2 执行自动生图脚本**：

```bash
COVER_PROMPT_COUNT=$(find "$ARTICLE_DIR/02-cover/prompts" -name "*.md" | wc -l | tr -d ' ')
IMAGE_PROMPT_COUNT=$(find "$ARTICLE_DIR/03-images/prompts" -name "*.md" | wc -l | tr -d ' ')

[ "$COVER_PROMPT_COUNT" = "0" ] && [ "$IMAGE_PROMPT_COUNT" = "0" ] && {
  echo "错误：没有找到图片提示词，请回到 Step 2 生成 Baoyu prompt。"
  exit 1
}

python3 "{skill_dir}/scripts/generate-images-myweb3.py" "$ARTICLE_DIR"
```

脚本可选参数：

```bash
python3 "{skill_dir}/scripts/generate-images-myweb3.py" "$ARTICLE_DIR" \
  --api-base "$IMAGE_API_BASE" \
  --model "${IMAGE_MODEL:-gpt-image-2}" \
  --cover-size "${COVER_IMAGE_SIZE:-1808x768}" \
  --image-size "${ARTICLE_IMAGE_SIZE:-1536x864}" \
  --retries 2
```

**3.3 生成结果检查**：

```bash
COVER_EXISTS=$(find "$ARTICLE_DIR/02-cover" -maxdepth 1 \( -name "cover.png" -o -name "cover.jpg" -o -name "cover.jpeg" -o -name "cover.webp" \) | head -1)
IMAGE_COUNT=$(find "$ARTICLE_DIR/03-images" -maxdepth 1 \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.webp" \) | wc -l | tr -d ' ')

[ -z "$COVER_EXISTS" ] && {
  echo "警告：未生成封面图，继续发布会使用默认封面。"
}
```

| 情况 | 处理 |
|------|------|
| API Key 缺失 | 停止，提示配置 `IMAGE_API_KEY` 或 `MYWEB3_API_KEY`，在 meta.yaml 记录 `status: image_failed` |
| myweb3 重试后仍失败 | 停止，记录 `image_error`，保持 prompt 文件不变，之后可从 Step 3 恢复 |
| 封面图缺失但正文图已生成 | 可继续 Step 4；发布时无 `--cover` 参数，微信会显示默认封面 |
| 图片已存在 | 默认跳过不覆盖；需要重生成时用 `--force` |

脚本成功后更新 meta.yaml：

```yaml
status: "images_ready"
cover_images: true
body_images: {IMAGE_COUNT}
image_backend: "myweb3"
image_model: "{IMAGE_MODEL}"
```

**进度：Step 3 -> completed**

---

### Step 4: 格式化 + 插图

**进度：Step 4 -> in_progress**

**4.1 如果有配图，先插入 Markdown 引用**：

读取 `{ARTICLE_DIR}/03-images/outline.md`，根据每张配图的「Position」字段，
在 `draft.md` 对应段落后插入图片引用。图片文件按 `{ARTICLE_DIR}/03-images/` 下的 `.png/.jpg/.jpeg/.webp` 排序匹配，引用真实文件名，不要假设固定为 `.jpeg`：

```markdown
![{配图描述}](../03-images/{actual_filename})
```

保存为 `{ARTICLE_DIR}/01-article/draft-with-images.md`（有配图时）
或直接使用 `draft.md`（无配图时）。

**4.2 调用 baoyu-format-markdown**：

定位 baoyu-format-markdown：
```bash
FORMAT_SKILL=$(find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "SKILL.md" \
  -path "*/baoyu-format-markdown/*" 2>/dev/null | head -1 | xargs dirname)
BUN_X="bun"; command -v bun &>/dev/null || BUN_X="npx -y bun"
```

调用 baoyu-format-markdown skill，输入为 `draft-with-images.md`（或 `draft.md`），
传入 `auto_select: true`（自动选标题，不打断流程）。

格式化完成后，把输出文件复制到 pipeline 目录：

```bash
# format-markdown 输出为 {原文件名}-formatted.md
cp "{原文件}-formatted.md" "$ARTICLE_DIR/01-article/draft-formatted.md"
```

**更新 meta.yaml** `status: "formatted"`

**进度：Step 4 -> completed**

---

### Step 5: 转换 HTML

**进度：Step 5 -> in_progress**

定位 baoyu-markdown-to-html：
```bash
HTML_SKILL=$(find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "SKILL.md" \
  -path "*/baoyu-markdown-to-html/*" 2>/dev/null | head -1 | xargs dirname)
BUN_X="bun"; command -v bun &>/dev/null || BUN_X="npx -y bun"
```

调用 baoyu-markdown-to-html skill，输入 `{ARTICLE_DIR}/01-article/draft-formatted.md`。
主题从 baoyu-post-to-wechat 的 EXTEND.md 中读取（`default_theme`），不存在则用 `default`。

```bash
THEME=$(grep -m1 "^default_theme:" \
  "$HOME/.baoyu-skills/baoyu-post-to-wechat/EXTEND.md" 2>/dev/null \
  | awk '{print $2}' | tr -d '"' || echo "default")

$BUN_X "$HTML_SKILL/scripts/main.ts" \
  "$ARTICLE_DIR/01-article/draft-formatted.md" \
  --theme "$THEME"
```

输出自动生成到同目录（`draft-formatted.html`）。

**更新 meta.yaml** `status: "html_ready"`

**进度：Step 5 -> completed**

---

### Step 6: 发布草稿箱

**进度：Step 6 -> in_progress**

> **关键**：本步骤强制使用 `npx --yes tsx`，**不使用** bun（bun 在本环境无法访问外网）。

**6.1 定位 wechat-api.ts**：

```bash
WECHAT_API=$(find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "wechat-api.ts" \
  2>/dev/null | head -1)
[ -z "$WECHAT_API" ] && {
  echo "错误：找不到 wechat-api.ts，请确认 baoyu-post-to-wechat skill 已安装"
  exit 1
}
```

**6.2 加载凭证**（按 baoyu-post-to-wechat 的优先级）：

```bash
# 依次检查三个位置
for ENV_PATH in \
  ".baoyu-skills/.env" \
  "$HOME/.config/baoyu-skills/.env" \
  "$HOME/.baoyu-skills/.env"; do
  [ -f "$ENV_PATH" ] && { source "$ENV_PATH"; break; }
done

[ -z "$WECHAT_APP_ID" ] || [ -z "$WECHAT_APP_SECRET" ] && {
  echo "错误：微信 API 凭证未配置。"
  echo "请先运行 baoyu-post-to-wechat skill 完成首次配置，再使用 pipeline 发布。"
  exit 1
}
```

**6.3 读取发布参数**：

```bash
TITLE=$(python3 -c "
import sys, yaml
m = yaml.safe_load(open('$ARTICLE_DIR/meta.yaml'))
print(m.get('title','') or '')
")
SUMMARY=$(python3 -c "
import sys, yaml
m = yaml.safe_load(open('$ARTICLE_DIR/meta.yaml'))
print(m.get('summary','') or '')
")
COVER=$(find "$ARTICLE_DIR/02-cover" -maxdepth 1 \( -name "cover.png" -o -name "cover.jpg" -o -name "cover.jpeg" -o -name "cover.webp" \) | head -1)
THEME=$(grep -m1 "^default_theme:" \
  "$HOME/.baoyu-skills/baoyu-post-to-wechat/EXTEND.md" 2>/dev/null \
  | awk '{print $2}' | tr -d '"' || echo "default")
```

**6.4 执行发布**：

```bash
PUBLISH_CMD="npx --yes tsx \"$WECHAT_API\" \
  \"$ARTICLE_DIR/01-article/draft-formatted.md\" \
  --theme \"$THEME\""

[ -n "$TITLE" ]   && PUBLISH_CMD="$PUBLISH_CMD --title \"$TITLE\""
[ -n "$SUMMARY" ] && PUBLISH_CMD="$PUBLISH_CMD --summary \"$SUMMARY\""
[ -n "$COVER" ] && [ -f "$COVER" ] && PUBLISH_CMD="$PUBLISH_CMD --cover \"$COVER\""

eval $PUBLISH_CMD
```

**6.5 提取 media_id，更新 meta.yaml**：

从命令输出中找 `media_id` 字段，更新 meta.yaml：

```yaml
status: "published"
media_id: "{提取到的 media_id}"
published_at: "{ISO 8601 时间}"
```

**6.6 完成报告**：

```
发布完成！

标题：{title}
摘要：{summary}
media_id：{media_id}

文章目录：{ARTICLE_DIR}
草稿箱：https://mp.weixin.qq.com → 内容管理 → 草稿箱

建议后续步骤：
→ 在草稿箱检查排版，可直接在微信编辑器修改
→ 修改完说「学习我的修改」让 wewrite 学习你的风格
```

**进度：Step 6 -> completed**

---

## 恢复模式

传入已有文章目录时，读取 `meta.yaml` 的 `status` 字段，从对应步骤继续：

| status | 继续位置 | 说明 |
|--------|---------|------|
| `init` | Step 1 | transcript 已就位，还未写作 |
| `drafted` | Step 1.5 | 原稿已有，先做独立文章来源框架校验，再生成提示词 |
| `prompts_ready` | Step 3 | 提示词已有，需要自动生成图片 |
| `image_failed` | Step 3 | 上次 myweb3 生成失败，修复配置或稍后重试 |
| `images_ready` | Step 4 | 图片已生成，需要格式化 |
| `formatted` | Step 5 | 已格式化，需要转 HTML |
| `html_ready` | Step 6 | HTML 已有，需要发布 |
| `published` | 询问 | 已发布，询问是否要重新发布 |

---

## 错误处理

| 步骤 | 错误 | 处理 |
|------|------|------|
| Step 0 | 目录已存在 | 询问是覆盖还是换新 slug |
| Step 0 | markitdown 不可用 | 直接复制 VTT，继续（wewrite 能处理原始字幕格式）|
| Step 1 | wewrite 输出文件找不到 | 提示用户手动指定 draft.md 路径 |
| Step 1 | python3 / yaml 不可用 | 跳过 meta.yaml 更新，手动从 frontmatter 读取 |
| Step 2 | baoyu skill 定位失败 | 停止；不能跳过 Baoyu 模板生成，记录错误后等待安装 / 指定 skill 路径 |
| Step 3 | 图片 API Key 缺失 | 停止，提示配置 `IMAGE_API_KEY` 或 `MYWEB3_API_KEY`，记录 `status: image_failed` |
| Step 3 | myweb3 超时 / 5xx / 524 | 自动重试；仍失败则记录 `image_error`，从 Step 3 恢复 |
| Step 3 | 无封面图 | 继续，发布时微信显示默认封面 |
| Step 6 | 凭证缺失 | 引导用户先运行 baoyu-post-to-wechat skill 配置 |
| Step 6 | npx 不可用 | 提示安装 Node.js：`brew install node` |
| 任意步骤 | 未知错误 | 在 meta.yaml `errors` 列表追加错误信息，告知用户当前 status，可手动恢复 |

---

## 注意事项

- **bun 网络**：baoyu-format-markdown 和 baoyu-markdown-to-html 的脚本只做本地处理，使用 `bun` 或 `npx -y bun` 均可，不受网络限制。只有 `wechat-api.ts` 需要网络，必须用 `npx --yes tsx`。
- **图片路径**：配图使用相对路径引用（`../03-images/`），支持 `.png/.jpg/.jpeg/.webp`，确保 HTML 转换后图片可被 wechat-api.ts 正确上传。
- **图片格式**：myweb3 的 `b64_json` 输出按 PNG 保存；不要把 PNG 字节保存成 `.jpeg` 后缀。
- **首次使用**：需要先通过 baoyu-post-to-wechat skill 完成 API 凭证配置，pipeline 直接复用这份配置。
