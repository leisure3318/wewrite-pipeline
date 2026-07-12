---
name: wewrite-pipeline
description: |
  公众号内容全流程 pipeline：视频字幕 / 本地文稿 / 网页 URL → 微信草稿箱。
  自动初始化每篇文章的隔离目录结构，串联 wewrite（写作）+
  baoyu-cover-image（封面提示词）+ baoyu-article-illustrator（配图提示词）+
  baoyu-format-markdown（格式化）+ baoyu-markdown-to-html（排版）+
  baoyu-post-to-wechat（发布），并通过可配置的图片 API 自动生成封面和正文配图。
  触发词：wewrite-pipeline、全流程、pipeline、一键发布、字幕转公众号、网页转公众号、博客转公众号
user_invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# WeWrite Pipeline — 公众号全流程编排

## 概述

将「有原始素材」到「草稿箱」之间所有重复步骤自动化。图片提示词仍由 Baoyu 原始模板生成，随后通过用户配置的 OpenAI 兼容图片 API 自动生成封面和正文配图。

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
    │   └── cover.png            # 已配置图片 API 自动生成
    ├── 03-images/
    │   ├── outline.md           # 配图规划
    │   ├── prompts/
    │   │   ├── 01-{type}-{slug}.md
    │   │   └── ...              # 各张配图提示词
    │   └── *.png                # 已配置图片 API 自动生成
    └── meta.yaml                # 文章元数据和流程状态
```

---

## 行为声明

- **默认全自动**：Step 0 → Step 6 连续运行；YouTube 字幕下载和缺少必要 API 凭证除外。
- **自动图片生成**：Step 3 读取 Step 2 产出的 Baoyu prompt 文件，通过用户配置的 OpenAI 兼容 `/images/generations` 图片 API 自动生成图片。
- **图片外发授权**：默认要求每篇文章在 Step 3 前获得本篇明确授权；如果本机配置 `~/.baoyu-skills/wewrite-pipeline/EXTEND.md` 中设置 `image_prompt_auto_consent: true`（或兼容旧的 `myweb3_prompt_auto_consent: true`），则视为用户对普通公众号文章图片 prompt 的长期授权，可自动进入 Step 3。自动授权不适用于明确要求保密、包含密钥/凭证/客户资料/私密聊天/未公开商业资料的素材；这些情况仍必须暂停并请求单篇授权。
- **图片提示词硬约束**：Step 2 必须使用 baoyu-cover-image / baoyu-article-illustrator 的原始 skill 模板生成或重建提示词；禁止用临时手写、口述简化版、自由发挥版替代 baoyu 模板。
- **图片 API 配置**：Step 3 读取 `IMAGE_API_BASE`、`IMAGE_API_KEY` 和 `IMAGE_MODEL`；可选 `IMAGE_API_BACKEND`（写入元数据的服务商标识）、`COVER_IMAGE_SIZE`、`ARTICLE_IMAGE_SIZE`。接口需要兼容 OpenAI `/images/generations`。尺寸会向上取整为 16 的倍数。为了不影响旧环境，未设置 `IMAGE_API_BASE` 时仍回退到历史默认值，`MYWEB3_API_KEY` 仍作为旧配置别名支持。
- **网络限制规避**：发布步骤强制使用 `npx --yes tsx` 调用 `wechat-api.ts`，禁止使用 `bun`（bun 出口网络在本环境被系统拦截）。
- **内容来源隐身硬约束**：YouTube / 字幕 / 访谈 / 文稿 / 网页博客原文只能作为素材来源。除非用户明确要求写观后感、解读、逐字稿、来源评述或翻译，公开正文必须写成独立公众号文章，禁止用“看完这个视频 / 视频作者说 / 视频里 / 字幕里 / 作者说 / 原文写道 / 原作者认为 / 这篇博客提到”等来源框架。
- **观点型写作硬约束**：Step 1 不得把素材改写成中性摘要或信息搬运。正文必须形成清晰作者立场，至少包含中心判断、理由链条、风险边界或反对意见回应；可以吸收素材事实，但必须输出独立观点。
- **WeWrite 写作规则同步**：Step 1 调用 `wewrite` 前必须加载本机最新 `wewrite` skill 的 `writing-guide.md`、`playbook.md`、`history.yaml`、`style.yaml`、persona、范文/种子段落，以及 upstream 新增的 `persona-selection.md`、`realtime-check.md`、`commands.md`（存在时）；这些规则是语言质量和风格底线，pipeline 的独立文章/观点/总结约束是额外覆盖。
- **WeWrite 验证同步**：Step 1.5 除独立文章来源、观点和总结外，还必须执行 WeWrite 的禁用词、句长方差、段落节奏、具体性、情绪极性、分段实时自检和 `humanness_score.py` 辅助验证；只修具体问题段落，不整篇重写。
- **末尾总结硬约束**：除非用户明确要求不要总结，Step 1 生成的 `draft.md` 末尾必须包含 `## 总结` 或等价总结段，提炼 3-5 条可复述结论，不能只用一句口号收尾。
- **标题候选硬约束**：Step 1 写完正文后必须增加“标题候选生成 / 标题党优化”小步骤，读取 `baoyu-format-markdown/references/title-formulas.md`，产出 5 个标题候选，并默认选择最强标题写回 frontmatter、H1 和 `meta.yaml`。
- **路径约定**：本文档中 `{ARTICLE_DIR}` 指当次运行的文章根目录，`{skill_dir}` 指本 SKILL.md 所在目录。
- **读取/检查约定**：本文档中 `读取: <路径>` / `检查: <路径>` = 用当前 harness 的文件读取工具真实打开该文件、读完其全部内容，然后再继续依赖该文件的步骤；不同环境工具名不同，按本环境对应工具执行。
- **Python 解释器约定**：调用 WeWrite 自带脚本时，所有 `python3` 命令优先解析为 `$WEWRITE_SKILL/.venv/bin/python3`（若存在），否则回退系统 `python3`；pipeline 自带脚本仍可用系统 `python3`，除非本机另有 venv 配置。
- **进度追踪**：在 Codex 中优先用 `update_plan` 创建/更新步骤；不可用时用简短文本进度列表，完成一步标记一步。编号清单只是排序骨架，不依赖特定任务工具。

---

## 调用格式

```
$wewrite-pipeline <素材> [slug]
# 或直接用自然语言：把 <素材> 跑完整公众号 pipeline
```

| 参数 | 说明 |
|------|------|
| `<素材>` | 本地 `.md` / `.vtt` 文件路径、YouTube URL，或普通 Web URL |
| `[slug]` | 可选，英文 kebab-case（2-4 词）。不传则从内容自动推断 |

**示例**：
```bash
$wewrite-pipeline ~/Downloads/video-transcript.md claude-regression-2026
$wewrite-pipeline "https://youtube.com/watch?v=xxx" ai-new-features
$wewrite-pipeline "https://example.com/blog/post" web-article-topic
$wewrite-pipeline ~/wewrite-articles/2026-05-01-my-topic   # 恢复模式
```

---

## 主管道

### 启动时创建任务

```
Plan item: "Step 0: 初始化目录"
Plan item: "Step 1: wewrite 写作"
Plan item: "Step 1.6: 标题候选生成 / 标题党优化"
Plan item: "Step 2: 生成图片提示词"
Plan item: "Step 3: 自动生成图片（已配置图片 API）"
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
| YouTube URL | 匹配 `https?://(www\.)?youtu(be\.com\|\.be)/` | 输出 yt-article 命令，等待用户 |
| 其他 Web URL | 匹配 `https?://` 但**不匹配** YouTube | **不暂停**，按 0.2b 自动抓取保存为 `00-source/transcript.md` |
| 已有文章目录 | `test -d <path>/00-source` | 进入恢复模式（见文末）|

**0.2 YouTube 暂停提示**（仅 YouTube URL 输入时）：

```
检测到 YouTube URL，字幕需在你的终端下载（沙箱网络限制）。

请运行（约 10 秒）：

  yt-article "<YouTube URL>" "<slug>"

完成后字幕保存到 ~/wewrite-articles/<slug>/00-source/，
告诉我「字幕已就绪」或直接把路径发过来，pipeline 继续。

没有 yt-article 命令？在 ~/.zshrc 加入（见 README.md 的安装说明）。
```

**0.2b 普通 Web URL 抓取**（仅非 YouTube web URL 输入时，**不暂停**，全自动）：

不同于 YouTube，普通 web URL（博客文章、新闻、文档等）由 pipeline 直接抓取，不需要用户在终端操作。

**主路径**：baoyu-url-to-markdown 的 `baoyu-fetch` CLI（Chrome CDP + 站点适配器，输出最干净的 markdown）：

```bash
URL2MD_SKILL=$(find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -name "SKILL.md" -path "*/baoyu-url-to-markdown/*" 2>/dev/null | head -1 | xargs dirname)
BAOYU_FETCH="$URL2MD_SKILL/scripts/baoyu-fetch"

# 首次使用需安装依赖
[ -d "$URL2MD_SKILL/scripts/node_modules" ] || bun install --cwd "$URL2MD_SKILL/scripts"

# 抓取，30 秒超时
"$BAOYU_FETCH" "$URL" --output "$ARTICLE_DIR/00-source/transcript.md" --timeout 30000 2>&1 | tee /tmp/baoyu-fetch.log
```

**降级路径**：baoyu-fetch 的 Chrome CDP 在部分环境（沙箱、Linux server）启动失败时，**直接、静默**降级到 agent 的 `WebFetch` 工具，不需要询问用户：

- 调 `WebFetch`，传入 URL 与 prompt：「请把这篇文章完整内容输出为干净的 markdown，要求保留标题/作者/日期/正文/列表/引用，不要总结、不要省略、不要解读」
- 把返回的 markdown 写入 `$ARTICLE_DIR/00-source/transcript.md`
- 在 `meta.yaml` 记录 `fetch_method: webfetch`，主路径成功时记 `fetch_method: baoyu-fetch`

**slug 自动推断**（用户没传 slug 时）：取 URL path 最后一段（去掉 `.html` / `.htm` 等后缀），转 kebab-case；如果 path 是 `/` 或太短（< 3 字符），改用页面 H1 标题前 2-4 个英文/数字词。

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

**Step 1.0: 加载最新 WeWrite 写作上下文**：

在调用 wewrite 前，先定位当前安装的 wewrite skill，并把最新写作规则作为本次写作 prompt 的硬上下文；不要复制旧版规则到 pipeline 里长期漂移。

```bash
WEWRITE_SKILL=$(find ~/.agents/skills ~/.codex/skills ~/.claude/skills -maxdepth 2 \
  -name "SKILL.md" -path "*/wewrite/SKILL.md" 2>/dev/null | head -1 | sed 's#/SKILL.md$##')

[ -z "$WEWRITE_SKILL" ] && {
  echo "错误：找不到 wewrite skill，不能继续生成文章。"
  exit 1
}

WEWRITE_PY="$WEWRITE_SKILL/.venv/bin/python3"
[ -x "$WEWRITE_PY" ] || WEWRITE_PY="python3"

sed -n '1,140p' "$WEWRITE_SKILL/SKILL.md"
sed -n '217,370p' "$WEWRITE_SKILL/SKILL.md"
sed -n '1,340p' "$WEWRITE_SKILL/references/writing-guide.md"
[ -f "$WEWRITE_SKILL/references/persona-selection.md" ] && sed -n '1,220p' "$WEWRITE_SKILL/references/persona-selection.md"
[ -f "$WEWRITE_SKILL/references/realtime-check.md" ] && sed -n '1,220p' "$WEWRITE_SKILL/references/realtime-check.md"
[ -f "$WEWRITE_SKILL/references/commands.md" ] && sed -n '1,180p' "$WEWRITE_SKILL/references/commands.md"
[ -f "$WEWRITE_SKILL/playbook.md" ] && sed -n '1,220p' "$WEWRITE_SKILL/playbook.md"
[ -f "$WEWRITE_SKILL/history.yaml" ] && tail -80 "$WEWRITE_SKILL/history.yaml"
```

必须同步执行 WeWrite 最新 Step 4/5 写作约束：

- 读取 `style.yaml` 的 `writing_persona`；如果没有固定 persona，则读取 `references/persona-selection.md`（存在时），按素材主题自动匹配 top 2，并结合 `history.yaml` 最近 3 篇 persona 降权，避免连续重复；匹配不明确时默认 `midnight-friend`。
- 读取最终选定的 `personas/{persona}.yaml`；persona 是写作硬约束，不能只读文件名。
- 若 `references/exemplars/index.yaml` 存在，按当前文章类型注入范文片段；没有范文库时读取 `references/exemplar-seeds.yaml`，从开头、情绪段、转折、收尾各抽 1 个结构模式。
- 从叙事视角、时间线、类比域、情绪基调、节奏中随机激活 2-3 个表达维度；参考 `history.yaml`，避免连续使用同一组合和同一收尾类型。
- 读取 `references/realtime-check.md`（存在时），每写完约 500 字或一个 H2 后执行分段自检；问题当场修，不等到全文写完。
- 优先级固定为：`playbook.md`（confidence >= 5）> persona > 范文风格 > `writing-guide.md` > pipeline 的主题约束。
- pipeline 的“独立文章来源”“必须发表观点”“末尾总结”和“标题候选”约束是额外硬约束，不能被 persona、范文或 WeWrite 默认流程覆盖。
- WeWrite upstream 新增容器 `:::highlight`、`:::summary` 可作为可选排版元素；不得为了炫技强塞容器。

**调用 wewrite 时的指令**：

> 这是一篇视频字幕 / 文稿内容，已有明确选题和素材。
> 请跳过选题和热点抓取（Step 2），直接从框架选择（Step 3）开始，
> 把这份素材当作内容基础，完成写作和质量验证流程。
> 请严格执行当前最新 WeWrite Step 4/5：真实读取 writing-guide、playbook、history、persona、范文/种子段落、persona-selection、realtime-check；执行人格选择、history 去重、分段实时自检、快速自检、质量验证和 humanness_score 辅助检查。
> **公开正文必须是独立公众号文章**：素材来源可以保留在 frontmatter / meta.yaml，正文不得写成“看完视频后的感想”、不得出现“视频作者说 / 视频里 / 字幕里 / 这个视频”等来源框架；除非用户明确要求观后感或来源评述。
> **必须发表观点**：不要只复述素材，也不要写成中性摘要。请提炼一个可争辩、可展开的中心判断，并在正文中给出理由链条、具体场景、反对意见或风险边界；让读者读完知道作者到底赞成什么、反对什么、提醒什么。
> **末尾必须总结**：正文最后增加 `## 总结`，用 3-5 条短结论收束全文，提炼可复述观点和行动启发。
> **快速自检后再保存**：保存前扫描禁用词、句长方差、段落节奏、开头钩子、具体细节、金句密度、情绪极性和平台硬限；只修具体不达标的句子/段落。
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

**Step 1.5b: 观点与总结校验**：

进入标题、图片提示词、格式化、HTML 和发布前，必须人工快速检查 `draft.md`：

- 是否有一句清晰中心判断，而不是“素材讲了什么”的摘要。
- 是否至少包含一个作者判断、一个风险边界或反对意见回应。
- 是否在末尾包含 `## 总结` 或等价总结段，并提炼 3-5 条结论。
- 是否没有把 `:::summary` 容器当成唯一总结；容器可以增强排版，但正文仍要有可读的总结段。

若缺少观点或总结，必须先重写 `draft.md`；不要继续 Step 1.6、Step 2 或发布。

**Step 1.5c: WeWrite 质量验证同步**：

进入标题、图片提示词、格式化、HTML 和发布前，必须按最新 WeWrite Step 5 做一次写作质量检查：

- 禁用词：扫描 `writing-guide.md` 2.1，命中数必须为 0。
- 句长方差：不能连续 3 句以上长度接近；每 500 字至少有明显长短落差。
- 段落节奏：不能连续 2 个相近长度段落；普通段落过长时先拆段。
- 情绪极性：至少 2 处真实质疑、担忧、吐槽或边界判断，不能全篇中性转述。
- 具体性：每 500 字至少 2 处具体细节；每个 H2 至少有 1 条来自原始素材的真实锚点。
- 内容质量：开头前 3 句必须有悬念/冲突/好奇心；全文至少有 1 句可独立截图传播的金句；观点不能是“两面都有道理”。
- 平台硬限：正文不超过 20000 字、图片不超过 10 张、表格不超过 4 列；未认证公众号不能保留外部链接。

同步运行脚本辅助验证；脚本缺失时不阻塞，但必须人工完成上面的逐项检查：

```bash
WEWRITE_SKILL=${WEWRITE_SKILL:-$(find ~/.agents/skills ~/.codex/skills ~/.claude/skills -maxdepth 2 \
  -name "SKILL.md" -path "*/wewrite/SKILL.md" 2>/dev/null | head -1 | sed 's#/SKILL.md$##')}

if [ -n "$WEWRITE_SKILL" ]; then
  WEWRITE_PY="${WEWRITE_PY:-$WEWRITE_SKILL/.venv/bin/python3}"
  [ -x "$WEWRITE_PY" ] || WEWRITE_PY="python3"
fi

if [ -n "$WEWRITE_SKILL" ] && [ -f "$WEWRITE_SKILL/scripts/humanness_score.py" ]; then
  "$WEWRITE_PY" "$WEWRITE_SKILL/scripts/humanness_score.py" "$ARTICLE_DIR/01-article/draft.md" --json
fi
```

若 `composite_score` >= 30，读取 `param_scores` 中最差的 1-3 项，逐项定向修复相关句子或段落；每轮最多改 3 处，最多 2 轮。不要为降分项整篇重写，也不要动已经通过的段落。

**Step 1.6: 标题候选生成 / 标题党优化**：

在正文确认通过后，必须读取 Baoyu 标题公式参考：

```bash
TITLE_FORMULAS=$(find ~/.codex/plugins/cache ~/.agents/plugins/cache ~/.claude/plugins/cache ~/.baoyu-skills -path "*/baoyu-format-markdown/references/title-formulas.md" 2>/dev/null | head -1)
[ -z "$TITLE_FORMULAS" ] && {
  echo "错误：找不到 baoyu-format-markdown/references/title-formulas.md，不能跳过标题候选步骤。"
  exit 1
}
sed -n '1,220p' "$TITLE_FORMULAS"
```

基于 `draft.md` 的中心论点、读者痛点和可兑现信息量，自动生成 5 个标题候选：

- 3 个 hook 标题：从 Subversive / Solution / Suspense / Concrete Number / Contrast / Result First / Rhetorical Question / Empathy 中选择最适合文章的公式。
- 2 个 straightforward 标题：一个描述型，一个结论型。
- 每个候选必须标注使用的公式和简短理由。
- 默认选出最强标题（通常更短、更具体、更有点击动机，但必须准确兑现正文内容），不打断流程；只有用户明确要求人工选择时才暂停。
- 中文公众号标题优先控制在约 30 字以内，避免空泛学术标题和纯震惊党。

把默认选中的标题写回 `{ARTICLE_DIR}/01-article/draft.md` 的 frontmatter `title` 和正文 H1，并同步更新 `meta.yaml`：

```bash
python3 - "$ARTICLE_DIR/01-article/draft.md" "$ARTICLE_DIR/meta.yaml" "$SELECTED_TITLE" <<'EOF'
import re, sys
from pathlib import Path
import yaml

draft_path = Path(sys.argv[1])
meta_path = Path(sys.argv[2])
selected_title = sys.argv[3]

content = draft_path.read_text(encoding="utf-8")
match = re.match(r"^---\n(.*?)\n---\n?", content, re.DOTALL)
if not match:
    raise SystemExit("draft.md missing YAML frontmatter")
frontmatter = yaml.safe_load(match.group(1)) or {}
frontmatter["title"] = selected_title
body = content[match.end():]
body = re.sub(r"^# .+$", f"# {selected_title}", body, count=1, flags=re.MULTILINE)
draft_path.write_text("---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n" + body.lstrip(), encoding="utf-8")

meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
meta["title"] = selected_title
meta["status"] = "titled"
meta_path.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
EOF
```

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
    meta['status'] = meta.get('status') or 'drafted'
    open(meta_path, 'w').write(yaml.dump(meta, allow_unicode=True, default_flow_style=False))
EOF
```

**进度：Step 1 -> completed**

---

### Step 2: 生成图片提示词

**进度：Step 2 -> in_progress**

> 本步骤只生成提示词文件，不调用任何图片生成 API。图片生成统一交给 Step 3 的图片 API 自动化脚本。

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

封面与正文配图提示词验收门槛：

```bash
python3 "{skill_dir}/scripts/validate-image-prompts.py" "$ARTICLE_DIR" --cover-only
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

若任一提示词缺少 YAML frontmatter 或缺少 type-specific 结构段落，视为生成失败；必须回到 baoyu-article-illustrator 模板重新生成/重建，不能用手写简化版补齐。

完整提示词验收门槛：

```bash
python3 "{skill_dir}/scripts/validate-image-prompts.py" "$ARTICLE_DIR"
```

**更新 meta.yaml** `status: "prompts_ready"`

**进度：Step 2 -> completed**

---

### Step 3: 自动生成图片（可配置图片 API）

**进度：Step 3 -> in_progress**

**3.0 授权检查**：

Step 3 会把 `{ARTICLE_DIR}/02-cover/prompts/*.md` 和 `{ARTICLE_DIR}/03-images/prompts/*.md` 的内容发送到用户配置的第三方图片 API。执行前必须满足其一：

- 当前对话中，用户已对本篇文章明确同意发送图片 prompt 到已配置的第三方图片 API。
- 本机配置 `~/.baoyu-skills/wewrite-pipeline/EXTEND.md` 存在并设置：

```yaml
image_prompt_auto_consent: true
```

旧的 `myweb3_prompt_auto_consent: true` 同样视为授权，保证已有本地配置不受影响。

长期授权只覆盖普通公众号文章的封面和正文配图 prompt。若素材或 prompt 明显包含密钥、token、密码、客户资料、私密聊天、未公开商业资料，或用户在当前任务中表达“不要外发 / 不要发第三方 / 仅本地处理”，必须忽略长期授权并暂停请求单篇授权。

读取 Step 2 生成的 Baoyu prompt 文件，调用已配置的 OpenAI 兼容图片 API 自动生成图片：

- 封面：读取 `{ARTICLE_DIR}/02-cover/prompts/*.md` 的第一份 prompt，生成 `{ARTICLE_DIR}/02-cover/cover.png`
- 正文配图：读取 `{ARTICLE_DIR}/03-images/prompts/*.md`，按文件名排序，生成 `{ARTICLE_DIR}/03-images/{prompt_stem}.png`
- 如果同名 `.png/.jpg/.jpeg/.webp` 已存在，默认跳过，避免覆盖手动修过的旧图；需要重生成时显式加 `--force`
- API 响应优先读取 `data[0].b64_json` 并保存为 PNG；如果返回 `url`，下载对应图片
- 请求超时时间 300 秒；只对 timeout 和 `500/502/503/504/524` 这类临时错误重试，重试间隔为 10 秒、20 秒

**3.1 环境变量要求**：

脚本会自动读取以下 `.env`，无需手动 `export`：

- 当前工作目录 `.env`
- `$XDG_CONFIG_HOME/baoyu-skills/.env` 或 `~/.config/baoyu-skills/.env`
- `~/.baoyu-skills/.env`

如需指定其它位置，再传 `--env-file`。

```bash
# 必填：按你的图片服务商填写
IMAGE_API_BASE="https://your-image-api.example/v1"
IMAGE_API_KEY="..."
IMAGE_MODEL="your-image-model"

# 可选
IMAGE_API_BACKEND="my-provider"
COVER_IMAGE_SIZE="1808x768"
ARTICLE_IMAGE_SIZE="1536x864"
```

本地服务 / 服务器环境可直接配置自己的 OpenAI 兼容代理：

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

python3 "{skill_dir}/scripts/generate-images.py" "$ARTICLE_DIR"
```

脚本可选参数：

```bash
python3 "{skill_dir}/scripts/generate-images.py" "$ARTICLE_DIR" \
  --env-file "$HOME/.baoyu-skills/.env" \
  --api-base "$IMAGE_API_BASE" \
  --model "$IMAGE_MODEL" \
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
| API 配置缺失 | 停止，提示配置 `IMAGE_API_BASE`、`IMAGE_API_KEY`、`IMAGE_MODEL`，在 meta.yaml 记录 `status: image_failed` |
| 图片 API 重试后仍失败 | 停止，记录 `image_error`，保持 prompt 文件不变，之后可从 Step 3 恢复 |
| 封面图缺失但正文图已生成 | 可继续 Step 4；发布时无 `--cover` 参数，微信会显示默认封面 |
| 图片已存在 | 默认跳过不覆盖；需要重生成时用 `--force` |
| 只重生成封面 | 使用 `--cover-only --force`，避免误覆盖正文配图 |
| 只重生成正文配图 | 使用 `--body-only --force`，保留已修过的封面 |

脚本成功后更新 meta.yaml：

```yaml
status: "images_ready"
cover_images: true
body_images: {IMAGE_COUNT}
image_backend: "{IMAGE_API_BACKEND}"
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
传入 `auto_select: true`（自动选标题，不打断流程）。默认加 `--no-spacing`，避免运行时临时拉取 `autocorrect-node`；只有确认依赖已安装或缓存时才开启 spacing。

```bash
$BUN_X "$FORMAT_SKILL/scripts/main.ts" \
  "{原文件}" \
  --no-spacing
```

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

if [ -z "$WECHAT_APP_ID" ] || [ -z "$WECHAT_APP_SECRET" ]; then
  echo "错误：微信 API 凭证未配置。"
  echo "请先运行 baoyu-post-to-wechat skill 完成首次配置，再使用 pipeline 发布。"
  exit 1
fi
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
| `image_failed` | Step 3 | 上次图片 API 生成失败，修复配置或稍后重试 |
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
| Step 0.2b | baoyu-fetch Chrome CDP 启动失败 / 超时 | 静默降级到 `WebFetch`，无需用户介入；记录 `fetch_method: webfetch` |
| Step 0.2b | WebFetch 也失败（网络/认证 URL） | 提示用户该 URL 需要登录或代理；让用户手动粘贴正文或换 URL |
| Step 1 | wewrite 输出文件找不到 | 提示用户手动指定 draft.md 路径 |
| Step 1.6 | 找不到 title-formulas.md | 停止；不能跳过标题候选步骤，先安装 / 指定 baoyu-format-markdown |
| Step 1 | python3 / yaml 不可用 | 跳过 meta.yaml 更新，手动从 frontmatter 读取 |
| Step 2 | baoyu skill 定位失败 | 停止；不能跳过 Baoyu 模板生成，记录错误后等待安装 / 指定 skill 路径 |
| 素材收集 | Reddit / 网页抓取被限制 | 记录抓取失败和替代来源；优先用用户提供正文、浏览器可见内容、截图或摘要继续，不把未验证 Reddit 评论写成事实 |
| Step 3 | 图片 API 配置缺失 | 停止，提示配置 `IMAGE_API_BASE`、`IMAGE_API_KEY`、`IMAGE_MODEL`，记录 `status: image_failed` |
| Step 3 | 图片 API 超时 / 5xx / 524 | 自动重试；仍失败则记录 `image_error`，从 Step 3 恢复 |
| Step 3 | 无封面图 | 继续，发布时微信显示默认封面 |
| Step 6 | 凭证缺失 | 引导用户先运行 baoyu-post-to-wechat skill 配置 |
| Step 6 | npx 不可用 | 提示安装 Node.js：`brew install node` |
| 任意步骤 | 未知错误 | 在 meta.yaml `errors` 列表追加错误信息，告知用户当前 status，可手动恢复 |

---

## 注意事项

- **bun 网络**：baoyu-format-markdown 和 baoyu-markdown-to-html 的脚本只做本地处理，使用 `bun` 或 `npx -y bun` 均可，不受网络限制。只有 `wechat-api.ts` 需要网络，必须用 `npx --yes tsx`。
- **图片路径**：配图使用相对路径引用（`../03-images/`），支持 `.png/.jpg/.jpeg/.webp`，确保 HTML 转换后图片可被 wechat-api.ts 正确上传。
- **图片格式**：图片 API 的 `b64_json` 输出按 PNG 保存；不要把 PNG 字节保存成 `.jpeg` 后缀。
- **首次使用**：需要先通过 baoyu-post-to-wechat skill 完成 API 凭证配置，pipeline 直接复用这份配置。
