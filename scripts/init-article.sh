#!/usr/bin/env bash
# init-article.sh — 初始化 wewrite-pipeline 文章目录结构
# 用法: init-article.sh <slug> [源文件路径]
# 示例: init-article.sh 2026-05-ai-features ~/Downloads/transcript.md

set -euo pipefail

SLUG="${1:-}"
SOURCE="${2:-}"

if [ -z "$SLUG" ]; then
  echo "用法: $0 <slug> [源文件路径]"
  echo "示例: $0 2026-05-ai-features ~/Downloads/transcript.md"
  exit 1
fi

DATE=$(date +%Y-%m-%d)
ARTICLE_DIR="$HOME/wewrite-articles/${DATE}-${SLUG}"

if [ -d "$ARTICLE_DIR" ]; then
  echo "⚠️  目录已存在: $ARTICLE_DIR"
  read -rp "继续（覆盖已有文件）？[y/N] " confirm
  [[ "$confirm" != "y" && "$confirm" != "Y" ]] && exit 0
fi

# 创建目录结构
mkdir -p "$ARTICLE_DIR/00-source"
mkdir -p "$ARTICLE_DIR/01-article"
mkdir -p "$ARTICLE_DIR/02-cover/prompts"
mkdir -p "$ARTICLE_DIR/03-images/prompts"

# 写入初始 meta.yaml
cat > "$ARTICLE_DIR/meta.yaml" <<EOF
slug: "$SLUG"
date: "$DATE"
source: "${SOURCE:-}"
status: "init"
title: null
summary: null
media_id: null
published_at: null
errors: []
EOF

# 如果提供了源文件，复制或转换
if [ -n "$SOURCE" ] && [ -f "$SOURCE" ]; then
  EXT="${SOURCE##*.}"
  if [ "$EXT" = "vtt" ] && command -v markitdown &>/dev/null; then
    markitdown "$SOURCE" -o "$ARTICLE_DIR/00-source/transcript.md"
    echo "✓ VTT → Markdown: 00-source/transcript.md"
  else
    cp "$SOURCE" "$ARTICLE_DIR/00-source/transcript.md"
    echo "✓ 源文件已复制: 00-source/transcript.md"
  fi
fi

echo ""
echo "✓ 文章目录已初始化: $ARTICLE_DIR"
echo ""
echo "目录结构:"
find "$ARTICLE_DIR" -type d | sed "s|$HOME|~|g" | sort
echo ""
echo "下一步: 在 Claude Code 中运行"
echo "  /wewrite-pipeline $ARTICLE_DIR"
