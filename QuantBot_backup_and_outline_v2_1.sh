#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="/www/wwwroot/QuantBot"
BACKUP_ROOT="/www/wwwroot/QuantBot_Backups"
DOCS_DIR="${PROJECT}/docs"

TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"

FULL_BACKUP="${BACKUP_ROOT}/QuantBot_FULL_${TIMESTAMP}.tar.gz"
STATE_BACKUP="${BACKUP_ROOT}/QuantBot_STATE_${TIMESTAMP}.tar.gz"
CHECKSUM_FILE="${BACKUP_ROOT}/SHA256_${TIMESTAMP}.txt"

OUTLINE_SOURCE="${PROJECT}/QuantBot_总体开发与研究大纲_V2.1_完整追加版.md"
OUTLINE_TARGET="${DOCS_DIR}/QuantBot_总体开发与研究大纲_V2.1.md"

echo "================================================================"
echo "QuantBot V2.1 项目阶段性备份"
echo "================================================================"
echo "项目目录: ${PROJECT}"
echo "备份目录: ${BACKUP_ROOT}"
echo "时间:      ${TIMESTAMP}"
echo

# ------------------------------------------------------------
# 1. 基础检查
# ------------------------------------------------------------

if [[ ! -d "${PROJECT}" ]]; then
    echo "ERROR: 项目目录不存在: ${PROJECT}"
    exit 1
fi

mkdir -p "${BACKUP_ROOT}"
mkdir -p "${DOCS_DIR}"

# ------------------------------------------------------------
# 2. 保存 V2.1 大纲
# ------------------------------------------------------------

if [[ -f "${OUTLINE_SOURCE}" ]]; then

    cp -a "${OUTLINE_SOURCE}" "${OUTLINE_TARGET}"

    echo "[OK] V2.1 大纲已保存:"
    echo "     ${OUTLINE_TARGET}"

else

    echo "[WARN] 未找到 V2.1 大纲源文件:"
    echo "       ${OUTLINE_SOURCE}"
    echo "       跳过大纲复制。"

fi

# ------------------------------------------------------------
# 3. 完整项目备份
#
# 备份：
#   quantbot
#   scripts
#   config*
#   data
#   docs
#   README*
#   requirements*
#   pyproject*
#   *.md
#   *.json
#
# 排除：
#   venv
#   .venv
#   __pycache__
#   *.pyc
#   .git
#   logs
#   临时目录
# ------------------------------------------------------------

echo
echo "[1/4] 创建完整项目备份..."

tar \
    --exclude='./venv' \
    --exclude='./.venv' \
    --exclude='./__pycache__' \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    --exclude='./.git' \
    --exclude='./logs' \
    --exclude='*/logs' \
    --exclude='./tmp' \
    --exclude='*/tmp' \
    -czf "${FULL_BACKUP}" \
    -C "$(dirname "${PROJECT}")" \
    "$(basename "${PROJECT}")"

echo "[OK] 完整备份:"
echo "     ${FULL_BACKUP}"

# ------------------------------------------------------------
# 4. 研究状态轻量备份
#
# 主要用于快速恢复：
#   quantbot
#   scripts
#   docs
#   data/reports
#   配置文件
#   README
# ------------------------------------------------------------

echo
echo "[2/4] 创建研究状态备份..."

tar \
    --exclude='./venv' \
    --exclude='./.venv' \
    --exclude='./__pycache__' \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    --exclude='./.git' \
    -czf "${STATE_BACKUP}" \
    -C "$(dirname "${PROJECT}")" \
    "$(basename "${PROJECT}")/quantbot" \
    "$(basename "${PROJECT}")/scripts" \
    "$(basename "${PROJECT}")/docs" \
    "$(basename "${PROJECT}")/data/reports" \
    "$(basename "${PROJECT}")/README"* \
    "$(basename "${PROJECT}")/requirements"* \
    "$(basename "${PROJECT}")/pyproject.toml" 2>/dev/null || true

echo "[OK] 状态备份:"
echo "     ${STATE_BACKUP}"

# ------------------------------------------------------------
# 5. SHA256 校验
# ------------------------------------------------------------

echo
echo "[3/4] 生成 SHA256 校验..."

sha256sum \
    "${FULL_BACKUP}" \
    "${STATE_BACKUP}" \
    > "${CHECKSUM_FILE}"

echo "[OK] SHA256:"
cat "${CHECKSUM_FILE}"

# ------------------------------------------------------------
# 6. 检查压缩包
# ------------------------------------------------------------

echo
echo "[4/4] 检查备份压缩包..."

if tar -tzf "${FULL_BACKUP}" >/dev/null; then
    echo "[OK] 完整备份压缩包检查通过"
else
    echo "[ERROR] 完整备份压缩包损坏"
    exit 1
fi

if tar -tzf "${STATE_BACKUP}" >/dev/null; then
    echo "[OK] 状态备份压缩包检查通过"
else
    echo "[ERROR] 状态备份压缩包损坏"
    exit 1
fi

# ------------------------------------------------------------
# 7. 输出结果
# ------------------------------------------------------------

echo
echo "================================================================"
echo "备份完成"
echo "================================================================"

echo
echo "完整备份:"
ls -lh "${FULL_BACKUP}"

echo
echo "状态备份:"
ls -lh "${STATE_BACKUP}"

echo
echo "校验文件:"
ls -lh "${CHECKSUM_FILE}"

echo
echo "V2.1 大纲:"
if [[ -f "${OUTLINE_TARGET}" ]]; then
    ls -lh "${OUTLINE_TARGET}"
else
    echo "未生成"
fi

echo
echo "================================================================"
echo "QUANTBOT_V2_1_BACKUP_OK"
echo "================================================================"
