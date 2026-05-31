#!/usr/bin/env bash
# ============================================================================
# StorageOps Skill Pack — Self-Diagnostic Health Check
# ============================================================================

SKILLS_DIR="${1:-$HOME/.pi/agent/skills}"
PASS=0
FAIL=0

echo "========================================="
echo "StorageOps Skill Pack — 健康检查"
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

# 3. References
echo ""
echo "--- 3. Reference 文档 ---"
REF_COUNT=$(find "$SKILLS_DIR" -name "*.md" -path "*/references/*" | wc -l | tr -d ' ')
echo "  📚 Reference 文档: $REF_COUNT"

# 4. Golden cases
echo ""
echo "--- 4. Golden Cases ---"
CASES_DIR="$SKILLS_DIR/storageops-eval-golden-cases/cases"
if [ -d "$CASES_DIR" ]; then
  CASE_COUNT=$(ls "$CASES_DIR" | wc -l | tr -d ' ')
  echo "  📋 Golden cases: $CASE_COUNT"
  
  # Check adversarial cases
  ADV_COUNT=$(ls "$CASES_DIR" | grep "adversarial" | wc -l | tr -d ' ')
  echo "  🛡️  Adversarial cases: $ADV_COUNT"
else
  echo "  ❌ Cases directory not found"
  FAIL=$((FAIL+1))
fi

# 5. Scripts
echo ""
echo "--- 5. 脚本 ---"
SCRIPT_COUNT=$(ls "$SKILLS_DIR/scripts/"*.sh "$SKILLS_DIR/scripts/"*.py 2>/dev/null | wc -l | tr -d ' ')
echo "  🔧 可执行脚本: $SCRIPT_COUNT"

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
