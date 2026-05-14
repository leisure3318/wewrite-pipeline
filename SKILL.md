---
name: wewrite-pipeline
description: |
  公众号内容全流程 pipeline：视频字幕 / 本地文稿 → 微信草稿箱。
  自动初始化每篇文章的隔离目录结构，串联 wewrite（写作）+
  AI检测 + 标题优化 + baoyu-cover-image（封面提示词）+
  baoyu-article-illustrator（配图提示词）+ baoyu-format-markdown（格式化）+
  baoyu-markdown-to-html（排版）+ baoyu-post-to-wechat（发布）。
  在图片生成处自然暂停等待用户，其余全自动。
  触发词：wewrite-pipeline、全流程、pipeline、一键发布、字幕转公众号
user_invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# WeWrite Pipeline — 公众号全流程编排

## 概述

将「有原始素材」到「草稿箱」之间所有重复步骤自动化，只保留一个必须人工介入的节点：**图片生成**（封面和配图需手动在 Gemini 等工具操作）。

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
    │   └── cover.jpeg           # 用户手动生成后放入
    ├── 03-images/
    │   ├── outline.md           # 配图规划
    │   ├── prompts/
    │   │   ├── 01-{type}-{slug}.md
    │   │   └── ...              # 各张配图提示词
    │   └── *.jpeg               # 用户手动生成后放入
    └── meta.yaml                # 文章元数据和流程状态
```

---

## 行为声明

- **默认全自动**：Step 0 → Step 2 连续运行，Step 3 手动暂停等图片，Step 4 → Step 6 继续全自动。
- **子技能禁止交互**：调用 wewrite、baoyu-cover-image、baoyu-article-illustrator、baoyu-format-markdown 时，pipeline 内部直接执行所有步骤，任何子技能不得触发 AskUserQuestion。wewrite 必须从框架选择直接运行到写作完成；baoyu-cover-image 和 baoyu-article-illustrator 的 EXTEND.md 已设 `quick_mode: true`；baoyu-format-markdown 使用 `auto_select: true`。
- **YouTube 字幕**：直接调用 yt-dlp 内联下载字幕，使用 `$HOME/.yt-cookies.txt` 认证，不等待用户手动运行 yt-article。如果 yt-dlp 失败，才提示用户手动运行。
- **网络限制规避**：发布步骤强制使用 `npx --yes tsx` 调用 `wechat-api.ts`，禁止使用 `bun`。
- **路径约定**：`{ARTICLE_DIR}` 指当次运行的文章根目录，`{skill_dir}` 指本 SKILL.md 所在目录。
- **进度追踪**：启动时用 TaskCreate 创建任务，完成一步标记一步。

---

## 调用格式

```
/wewrite-pipeline <素材> [slug]
```

| 参数 | 说明 |
|------|------|
| `<素材>` | 本地 `.md` / `.vtt` 文件路径，或 YouTube URL |
| `[slug]` | 可选，英文 kebab-case（2-4 词）。不传则从内容自动推断 |

**示例**：
```bash
/wewrite-pipeline ~/Downloads/video-transcript.md claude-regression-2026
/wewrite-pipeline "https://youtube.com/watch?v=xxx" ai-new-features
/wewrite-pipeline ~/wewrite-articles/2026-05-01-my-topic   # 恢复模式
```

---

## 主管道

### 启动时创建任务

```
TaskCreate: "Step 0: 初始化目录"
TaskCreate: "Step 1: wewrite 写作"
TaskCreate: "Step 1.4: AI 检测"
TaskCreate: "Step 1.5: 标题优化"
TaskCreate: "Step 2: 生成图片提示词"
TaskCreate: "Step 3: 等待图片（手动）"
TaskCreate: "Step 4: 格式化 + 插图"
TaskCreate: "Step 5: 转换 HTML"
TaskCreate: "Step 6: 发布草稿箱"
```

---

### Step 0: 初始化目录

**TaskUpdate: Step 0 → in_progress**

**0.1 输入类型检测**：

| 输入 | 检测规则 | 处理 |
|------|---------|------|
| 本地 `.md` 文件 | `test -f <path>` 且以 `.md` 结尾 | 复制到 `00-source/transcript.md` |
| 本地 `.vtt` 文件 | `test -f <path>` 且以 `.vtt` 结尾 | Python 解析转换为纯文本 |
| YouTube URL | 匹配 `https?://(www\.)?youtu(be\.com|\.be)/` | 直接调用 yt-dlp 下载（见 0.2）|
| 已有文章目录 | `test -d <path>/00-source` | 进入恢复模式（见文末）|

**0.2 YouTube 字幕下载**（仅 URL 输入时，直接执行，不等待用户）：

```bash
export http_proxy=http://127.0.0.1:7897 && export https_proxy=http://127.0.0.1:7897
OUTDIR="$ARTICLE_DIR/00-source"
mkdir -p "$OUTDIR"

yt-dlp \
  --cookies "$HOME/.yt-cookies.txt" \
  --write-auto-sub --sub-lang en \
  --skip-download --no-playlist \
  --output "$OUTDIR/%(title)s.%(ext)s" \
  "{YouTube URL}"

# 解析 VTT → 纯文本 transcript.md
VTT=$(ls "$OUTDIR"/*.vtt 2>/dev/null | head -1)
if [ -n "$VTT" ]; then
  python3 - "$VTT" "$OUTDIR/transcript.md" <<'EOF'
import re, sys
text = open(sys.argv[1], encoding='utf-8').read()
text = re.sub(r'^WEBVTT.*?\n\n', '', text, flags=re.DOTALL)
text = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> .*\n', '', text)
text = re.sub(r'<[^>]+>', '', text)
lines = [l.strip() for l in text.splitlines() if l.strip()]
deduped = [lines[0]] if lines else []
for l in lines[1:]:
    if l != deduped[-1]:
        deduped.append(l)
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(deduped) + '\n')
print(f"✓ transcript.md 已生成（{len(deduped)} 行）")
EOF
fi
```

如果 yt-dlp 失败，提示用户手动运行 `yt-article "{URL}" "{slug}"`，等待「继续」后恢复。

**0.3 VTT 文件转换**（本地 `.vtt` 输入时）：

```bash
python3 - "{input}" "$ARTICLE_DIR/00-source/transcript.md" <<'EOF'
import re, sys
text = open(sys.argv[1], encoding='utf-8').read()
text = re.sub(r'^WEBVTT.*?\n\n', '', text, flags=re.DOTALL)
text = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> .*\n', '', text)
text = re.sub(r'<[^>]+>', '', text)
lines = [l.strip() for l in text.splitlines() if l.strip()]
deduped = [lines[0]] if lines else []
for l in lines[1:]:
    if l != deduped[-1]:
        deduped.append(l)
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(deduped) + '\n')
EOF
```

**0.4 创建目录结构**：

```bash
DATE=$(date +%Y-%m-%d)
ARTICLE_DIR="$HOME/wewrite-articles/${DATE}-{slug}"

mkdir -p "$ARTICLE_DIR/00-source"
mkdir -p "$ARTICLE_DIR/01-article"
mkdir -p "$ARTICLE_DIR/02-cover/prompts"
mkdir -p "$ARTICLE_DIR/03-images/prompts"
```

如果目录已存在，直接继续（不覆盖已有内容）。

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

**TaskUpdate: Step 0 → completed**

---

### Step 1: 生成文章

**TaskUpdate: Step 1 → in_progress**

读取 `{ARTICLE_DIR}/00-source/transcript.md` 的内容，调用 **wewrite skill** 进行写作。

**调用 wewrite 时的指令**：

> 这是一篇视频字幕 / 文稿内容，已有明确选题和素材。
> 请跳过选题和热点抓取（Step 2），直接从框架选择（Step 3）开始，
> 把这份素材当作内容基础，完成写作和质量验证流程。
> **输出文件保存到 `{ARTICLE_DIR}/01-article/draft.md`**，
> 而不是 wewrite 的默认 output 目录。
> **全程不得触发任何 AskUserQuestion，所有决策自动执行。**

wewrite 完成后，确认 `{ARTICLE_DIR}/01-article/draft.md` 存在。
如果 wewrite 仍写入了默认目录，用以下命令找到并复制：

```bash
LATEST=$(find ~/.claude/skills/wewrite/output -name "*.md" \
  -not -name "*-formatted*" -newer "$ARTICLE_DIR/00-source/transcript.md" \
  2>/dev/null | sort | tail -1)

[ -n "$LATEST" ] && cp "$LATEST" "$ARTICLE_DIR/01-article/draft.md"
```

**更新 meta.yaml**：从 draft.md frontmatter 提取 title / summary：

```bash
python3 - "$ARTICLE_DIR/01-article/draft.md" "$ARTICLE_DIR/meta.yaml" <<'EOF'
import sys, re, yaml
draft_path, meta_path = sys.argv[1], sys.argv[2]
content = open(draft_path).read()
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if m:
    fm = yaml.safe_load(m.group(1))
    meta = yaml.safe_load(open(meta_path).read()) or {}
    meta['title'] = fm.get('title') or meta.get('title')
    meta['summary'] = fm.get('summary') or fm.get('description') or meta.get('summary')
    meta['status'] = 'drafted'
    open(meta_path, 'w').write(yaml.dump(meta, allow_unicode=True, default_flow_style=False))
EOF
```

**TaskUpdate: Step 1 → completed**

---

### Step 1.4: AI 检测

**TaskUpdate: Step 1.4 → in_progress**

对刚写完的草稿做人性化评分，识别需要修改的段落：

```bash
WEWRITE_DIR="$HOME/.claude/skills/wewrite"
python3 "$WEWRITE_DIR/scripts/humanness_score.py" \
  "$ARTICLE_DIR/01-article/draft.md" --verbose 2>/dev/null || \
echo "[AI检测] humanness_score.py 不可用，跳过"
```

**输出格式**（给用户看）：

```
AI 检测结果：
  综合得分：{score}/100（越低越像人写的）
  主要问题：
  - {top issue 1}（建议：{fix}）
  - {top issue 2}（建议：{fix}）
```

得分 < 30 → 继续；30-50 → 提示可在编辑锚点处补充个人内容；> 50 → 列出最影响得分的 2-3 处供参考（不阻断流程）。

**TaskUpdate: Step 1.4 → completed**

---

### Step 1.5: 标题优化

**TaskUpdate: Step 1.5 → in_progress**

基于文章内容，用以下公式生成 5 个爆款标题候选，**自动选得分最高的一个**更新 meta.yaml。同时输出完整候选供用户参考，用户可随时说「换标题 N」切换：

**公式库**（根据文章内容和 tone 各生成 1-2 个）：

| 公式 | 示例 |
|------|------|
| **结果先行** | 「把两个 AI 接在一起，我多出了 20% 的时间」 |
| **反问颠覆** | 「你还在单独用 Claude？你已经落后了」 |
| **悬念私密** | 「凌晨两点，我让 AI 做了这件事……」 |
| **数字承诺** | 「3 个 Claude 组合，20 分钟搭完每周自动跑」 |
| **对比锐切** | 「消费者用工具，高手用引擎——差距就在这里」 |
| **认知反转** | 「我用了半年才发现，之前 Claude 一直用错了」 |

**评分标准**（自动选择最高分）：
- 有数字或具体细节（+2分）
- 制造了好奇心或悬念（+2分）
- 暗示了利益/结果（+2分）
- 口语化、避开书面腔（+1分）
- 长度 15-30 字（+1分）

输出格式：

```
标题候选（已自动选择★）：
  ★ 1. {最高分标题}
     2. {候选2}
     3. {候选3}
     4. {候选4}
     5. {候选5}

已更新 meta.yaml。如需换标题，说「换标题 N」。
```

**TaskUpdate: Step 1.5 → completed**

---

### Step 2: 生成图片提示词

**TaskUpdate: Step 2 → in_progress**

> 本步骤只生成提示词文件，不调用任何图片生成 API。

**2.1 调用 baoyu-cover-image**（仅生成提示词）：

调用 baoyu-cover-image skill，传入 `{ARTICLE_DIR}/01-article/draft.md`，使用 `--quick` 跳过维度确认（EXTEND.md 已设 `quick_mode: true`，不会触发 AskUserQuestion）。

提示词文件生成后，确保它在 `{ARTICLE_DIR}/02-cover/prompts/` 下：

```bash
find "$HOME/.baoyu-skills/baoyu-cover-image/cover-image" -name "*.md" \
  -path "*/prompts/*" -newer "$ARTICLE_DIR/01-article/draft.md" 2>/dev/null \
  | while read f; do
  cp "$f" "$ARTICLE_DIR/02-cover/prompts/$(basename "$f")"
done
```

**2.2 调用 baoyu-article-illustrator**（仅生成提示词）：

调用 baoyu-article-illustrator skill，传入 `{ARTICLE_DIR}/01-article/draft.md`，density = balanced（3-5 张），`--quick`，在图片生成步骤前停止。

确保文件位置正确：

```bash
SRC_IMGS="$ARTICLE_DIR/01-article/imgs"
if [ -d "$SRC_IMGS" ]; then
  cp "$SRC_IMGS/outline.md" "$ARTICLE_DIR/03-images/" 2>/dev/null
  cp "$SRC_IMGS/prompts/"*.md "$ARTICLE_DIR/03-images/prompts/" 2>/dev/null
fi
```

**更新 meta.yaml** `status: "prompts_ready"`

**TaskUpdate: Step 2 → completed**

---

### Step 3: 等待图片（手动暂停）

**TaskUpdate: Step 3 → in_progress**

统计提示词数量，输出等待提示：

```bash
COVER_PROMPT_COUNT=$(find "$ARTICLE_DIR/02-cover/prompts" -name "*.md" | wc -l | tr -d ' ')
IMAGE_PROMPT_COUNT=$(find "$ARTICLE_DIR/03-images/prompts" -name "*.md" | wc -l | tr -d ' ')
```

```
图片提示词已全部生成！

📋 封面提示词（{COVER_PROMPT_COUNT} 个）：
   {ARTICLE_DIR}/02-cover/prompts/
   → 把生成的图片命名为 cover.jpeg 放到：
     {ARTICLE_DIR}/02-cover/cover.jpeg

📋 配图提示词（{IMAGE_PROMPT_COUNT} 个）：
   {ARTICLE_DIR}/03-images/prompts/
   → 把配图按 01-xxx.jpeg、02-xxx.jpeg 顺序放到：
     {ARTICLE_DIR}/03-images/

工作流：
  1. 打开 Gemini / ChatGPT / 其他图片生成工具
  2. 把提示词内容粘贴进去生成图片
  3. 下载后放到上面对应的路径

完成后说「继续」——只放封面图也可以先继续，配图可以后补。
```

**用户说「继续」后**，检查图片状态：

```bash
COVER_EXISTS=$(test -f "$ARTICLE_DIR/02-cover/cover.jpeg" && echo "yes" || echo "no")
IMAGE_COUNT=$(find "$ARTICLE_DIR/03-images" -maxdepth 1 -name "*.jpeg" | wc -l | tr -d ' ')
```

| 情况 | 处理 |
|------|------|
| `cover.jpeg` 存在 | 继续 Step 4 |
| `cover.jpeg` 不存在，用户确认跳过 | 继续，发布时微信显示默认封面，meta.yaml 记录 `no_cover: true` |
| `cover.jpeg` 不存在，用户没确认 | 再次提示，等待 |

**更新 meta.yaml** `status: "images_ready"`

**TaskUpdate: Step 3 → completed**

---

### Step 4: 格式化 + 插图

**TaskUpdate: Step 4 → in_progress**

**4.1 插入配图引用**：

读取 `{ARTICLE_DIR}/03-images/outline.md`，根据每张配图的「Position」字段，
在 `draft.md` 对应段落后插入图片引用：

```markdown
![{配图描述}](../03-images/{filename}.jpeg)
```

**4.2 调用 baoyu-format-markdown**：

调用 baoyu-format-markdown skill，输入为带图片引用的 `draft.md`，使用 `auto_select: true`（自动选标题，不打断流程）。

格式化完成后复制到 pipeline 目录：

```bash
cp "{原文件}-formatted.md" "$ARTICLE_DIR/01-article/draft-formatted.md"
```

**更新 meta.yaml** `status: "formatted"`

**TaskUpdate: Step 4 → completed**

---

### Step 5: 转换 HTML

**TaskUpdate: Step 5 → in_progress**

```bash
HTML_SKILL=$(find ~/.claude/plugins/cache/baoyu-skills -name "SKILL.md" \
  -path "*/baoyu-markdown-to-html/*" 2>/dev/null | head -1 | xargs dirname)
BUN_X="bun"; command -v bun &>/dev/null || BUN_X="npx -y bun"

THEME=$(grep -m1 "^default_theme:" \
  "$HOME/.baoyu-skills/baoyu-post-to-wechat/EXTEND.md" 2>/dev/null \
  | awk '{print $2}' | tr -d '"' || echo "default")

$BUN_X "$HTML_SKILL/scripts/main.ts" \
  "$ARTICLE_DIR/01-article/draft-formatted.md" \
  --theme "$THEME"
```

**更新 meta.yaml** `status: "html_ready"`

**TaskUpdate: Step 5 → completed**

---

### Step 6: 发布草稿箱

**TaskUpdate: Step 6 → in_progress**

> **关键**：本步骤强制使用 `npx --yes tsx`，**不使用** bun（bun 出口网络在本环境被系统拦截）。

**6.1 定位 wechat-api.ts**：

```bash
WECHAT_API=$(find ~/.claude/plugins/cache/baoyu-skills -name "wechat-api.ts" \
  2>/dev/null | head -1)
[ -z "$WECHAT_API" ] && {
  echo "错误：找不到 wechat-api.ts，请确认 baoyu-post-to-wechat skill 已安装"
  exit 1
}
```

**6.2 加载凭证**：

```bash
for ENV_PATH in ".baoyu-skills/.env" "$HOME/.config/baoyu-skills/.env" "$HOME/.baoyu-skills/.env"; do
  [ -f "$ENV_PATH" ] && { source "$ENV_PATH"; break; }
done

[ -z "$WECHAT_APP_ID" ] && {
  echo "错误：微信 API 凭证未配置。请先运行 /baoyu-post-to-wechat 完成配置。"
  exit 1
}
```

**6.3 执行发布**：

```bash
TITLE=$(python3 -c "import yaml; m=yaml.safe_load(open('$ARTICLE_DIR/meta.yaml').read()); print(m.get('title','') or '')")
SUMMARY=$(python3 -c "import yaml; m=yaml.safe_load(open('$ARTICLE_DIR/meta.yaml').read()); print(m.get('summary','') or '')")
COVER="$ARTICLE_DIR/02-cover/cover.jpeg"
THEME=$(grep -m1 "^default_theme:" "$HOME/.baoyu-skills/baoyu-post-to-wechat/EXTEND.md" 2>/dev/null | awk '{print $2}' | tr -d '"' || echo "default")

PUBLISH_CMD="npx --yes tsx \"$WECHAT_API\" \"$ARTICLE_DIR/01-article/draft-formatted.md\" --theme \"$THEME\""
[ -n "$TITLE" ]   && PUBLISH_CMD="$PUBLISH_CMD --title \"$TITLE\""
[ -n "$SUMMARY" ] && PUBLISH_CMD="$PUBLISH_CMD --summary \"$SUMMARY\""
[ -f "$COVER" ]   && PUBLISH_CMD="$PUBLISH_CMD --cover \"$COVER\""
eval $PUBLISH_CMD
```

**6.4 提取 media_id，更新 meta.yaml**：

```yaml
status: "published"
media_id: "{提取到的 media_id}"
published_at: "{ISO 8601 时间}"
```

**6.5 完成报告**：

```
发布完成！

标题：{title}
摘要：{summary}
media_id：{media_id}

文章目录：{ARTICLE_DIR}
草稿箱：https://mp.weixin.qq.com → 内容管理 → 草稿箱

→ 在草稿箱检查排版，可直接在微信编辑器修改
→ 修改完说「学习我的修改」让 wewrite 学习你的风格
```

**TaskUpdate: Step 6 → completed**

---

## 恢复模式

传入已有文章目录时，读取 `meta.yaml` 的 `status` 字段，从对应步骤继续：

| status | 继续位置 | 说明 |
|--------|---------|------|
| `init` | Step 1 | transcript 已就位，还未写作 |
| `drafted` | Step 1.4 | 原稿已有，运行 AI 检测 + 标题优化 |
| `prompts_ready` | Step 3 | 提示词已有，等待用户放图片 |
| `images_ready` | Step 4 | 图片已就位，需要格式化 |
| `formatted` | Step 5 | 已格式化，需要转 HTML |
| `html_ready` | Step 6 | HTML 已有，需要发布 |
| `published` | 询问 | 已发布，询问是否要重新发布 |

---

## 错误处理

| 步骤 | 错误 | 处理 |
|------|------|------|
| Step 0 | yt-dlp 不可用 | 提示用户手动运行 `yt-article`，等待「继续」 |
| Step 0 | markitdown 不可用 | 用 Python 直接解析 VTT，继续 |
| Step 1 | wewrite 输出文件找不到 | 提示用户手动指定 draft.md 路径 |
| Step 1.4 | humanness_score.py 不可用 | 跳过，不阻断流程 |
| Step 1.5 | 标题生成失败 | 保留原标题，继续 |
| Step 2 | baoyu skill 定位失败 | 跳过提示词生成，记录 `prompts_skipped: true`，继续 |
| Step 3 | 无封面图且用户确认跳过 | 继续，发布时微信显示默认封面 |
| Step 6 | 凭证缺失 | 引导用户先运行 `/baoyu-post-to-wechat` 配置 |
| Step 6 | npx 不可用 | 提示安装 Node.js：`brew install node` |
| 任意步骤 | 未知错误 | 在 meta.yaml `errors` 列表追加，告知当前 status，可手动恢复 |

---

## 注意事项

- **bun 网络**：baoyu-format-markdown 和 baoyu-markdown-to-html 只做本地处理，使用 `bun` 或 `npx -y bun` 均可。只有 `wechat-api.ts` 需要网络，必须用 `npx --yes tsx`。
- **图片路径**：配图使用相对路径引用（`../03-images/`），确保 HTML 转换后图片可被 wechat-api.ts 正确上传。
- **首次使用**：需要先通过 `/baoyu-post-to-wechat` 完成 API 凭证配置，pipeline 直接复用这份配置。
- **换标题**：说「换标题 N」可切换到 Step 1.5 生成的候选标题 N，并更新 meta.yaml。
- **Gemini 辅助工具**：`{skill_dir}/scripts/gemini_image_gen.py` 是可选的手动辅助脚本，不在主流程内自动调用。如需手动批量生图可自行运行：`python3 gemini_image_gen.py <prompt.md> <output.jpeg>`。
