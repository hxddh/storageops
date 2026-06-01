#!/usr/bin/env bash
# ============================================================================
# StorageOps Skill Pack — Self-Diagnostic Health Check
# ============================================================================
# 用法: ./scripts/skill-health-check.sh [skills-dir]
# 默认检测两种安装模式:
#   ~/.storageops/skills (独立模式, 优先)
#   ~/.pi/agent/skills   (合并模式)

# 自动检测 skills 目录
if [ -n "$1" ]; then
  SKILLS_DIR="$1"
elif [ -d "$HOME/.storageops/skills" ]; then
  SKILLS_DIR="$HOME/.storageops/skills"
elif [ -d "$HOME/.pi/agent/skills" ]; then
  SKILLS_DIR="$HOME/.pi/agent/skills"
else
  echo "错误: 未找到 StorageOps skills 目录"
  echo "  尝试: $HOME/.storageops/skills"
  echo "  尝试: $HOME/.pi/agent/skills"
  echo "  运行: storageops install 重新安装"
  exit 1
fi

PASS=0
FAIL=0

echo "========================================="
echo "StorageOps Skill Pack — 健康检查"
echo "Skills 目录: $SKILLS_DIR"
echo "========================================="

# 1. Skill count
echo ""
echo "--- 1. Skill 数量 ---"
COUNT=$(ls "$SKILLS_DIR" | grep "^storageops-" | wc -l | tr -d ' ')
if [ "$COUNT" -ge 9 ]; then
  echo "✅  Skill 数量: $COUNT (预期 >=9)"
  PASS=$((PASS+1))
else
  echo "❌  Skill 数量: $COUNT (预期 >=9)"
  FAIL=$((FAIL+1))
fi

# 2. SKILL.md validation
echo ""
echo "--- 2. SKILL.md 完整性 ---"
for skill in "$SKILLS_DIR"/storageops-*/; do
  name=$(basename "$skill")
  if [ ! -f "$skill/SKILL.md" ]; then
    echo "❌  $name: SKILL.md 缺失"
    FAIL=$((FAIL+1))
    continue
  fi

  # Check frontmatter
  has_name=$(head -5 "$skill/SKILL.md" | grep -c "^name:")
  has_desc=$(head -5 "$skill/SKILL.md" | grep -c "^description:")
  if [ "$has_name" -ge 1 ] && [ "$has_desc" -ge 1 ]; then
    echo "  ✅ $name"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name: frontmatter 不完整"
    FAIL=$((FAIL+1))
  fi
done

# 3. Skill name validity (Pi convention: a-z, 0-9, hyphens only)
echo ""
echo "--- 3. Skill 名称合法性 ---"
NAME_FAILS=0
for skill in "$SKILLS_DIR"/storageops-*/; do
  name=$(basename "$skill")
  frontmatter_name=$(grep "^name:" "$skill/SKILL.md" | head -1 | sed 's/name: *//')
  if ! echo "$frontmatter_name" | grep -qE '^[a-z0-9][a-z0-9-]*$'; then
    echo "  ❌ $name: name '$frontmatter_name' 含非法字符 (仅允许 a-z, 0-9, -)"
    NAME_FAILS=$((NAME_FAILS+1))
    FAIL=$((FAIL+1))
  fi
done
if [ "$NAME_FAILS" -eq 0 ]; then
  echo "  ✅ 全部名称合法"
  PASS=$((PASS+1))
fi

# 4. References
echo ""
echo "--- 4. Reference 文档 ---"
REF_COUNT=$(find "$SKILLS_DIR" -name "*.md" -path "*/references/*" | wc -l | tr -d ' ')
echo "  📚 Reference 文档: $REF_COUNT"

# 5. Golden cases
echo ""
echo "--- 5. Golden Cases ---"
CASES_DIR="$SKILLS_DIR/storageops-eval-golden-cases/cases"
if [ -d "$CASES_DIR" ]; then
  CASE_COUNT=$(ls "$CASES_DIR" | wc -l | tr -d ' ')
  echo "  📋 Golden cases: $CASE_COUNT"

  ADV_COUNT=$(ls "$CASES_DIR" | grep "adversarial" | wc -l | tr -d ' ')
  echo "  🛡️  Adversarial cases: $ADV_COUNT"
else
  echo "  ❌ Cases directory not found"
  FAIL=$((FAIL+1))
fi

# 6. Safety coverage
echo ""
echo "--- 6. 安全红线覆盖 ---"
REDLINE_COUNT=0
for skill in "$SKILLS_DIR"/storageops-*/; do
  if grep -q "绝对红线\|ABSOLUTELY\|credential-loader" "$skill/SKILL.md" 2>/dev/null; then
    REDLINE_COUNT=$((REDLINE_COUNT+1))
  fi
done
echo "  🔒 含安全红线: $REDLINE_COUNT/$COUNT skills"

# 7. Degradation coverage
echo ""
echo "--- 7. 降级诊断覆盖 ---"
DEGR_COUNT=0
for skill in "$SKILLS_DIR"/storageops-*/; do
  if grep -q "降级诊断\|Degradation Diagnosis" "$skill/SKILL.md" 2>/dev/null; then
    DEGR_COUNT=$((DEGR_COUNT+1))
  fi
done
echo "  📉 含降级诊断: $DEGR_COUNT/$COUNT skills"

# Summary
echo ""
echo "========================================="
echo "总结: $PASS 项通过, $FAIL 项失败"
echo "========================================="
