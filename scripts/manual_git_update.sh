#!/usr/bin/env bash
# Manual-only QuantBot code update.
# Run this on the server from /www/wwwroot/QuantBot after the repository
# has been connected to origin. It never resets, stashes, or overwrites
# untracked operational files such as .env, data, reports, or logs.
set -Eeuo pipefail

PROJECT_DIR="${1:-/www/wwwroot/QuantBot}"
BRANCH="${2:-main}"

if [[ ! -d "${PROJECT_DIR}/.git" ]]; then
    echo "ERROR: ${PROJECT_DIR} is not a Git working tree. Complete the one-time setup first."
    exit 1
fi

cd "${PROJECT_DIR}"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "ERROR: tracked local changes are present; refusing to overwrite them."
    git status --short
    exit 1
fi

git fetch --prune origin "${BRANCH}"

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse "origin/${BRANCH}")"

if [[ "${LOCAL_HEAD}" == "${REMOTE_HEAD}" ]]; then
    echo "QuantBot is already up to date: ${LOCAL_HEAD}"
    exit 0
fi

if ! git merge-base --is-ancestor "${LOCAL_HEAD}" "origin/${BRANCH}"; then
    echo "ERROR: local HEAD is not an ancestor of origin/${BRANCH}; refusing non-fast-forward update."
    echo "Inspect the divergence before resolving it manually."
    exit 1
fi

git merge --ff-only "origin/${BRANCH}"

PYTHON_BIN="${PROJECT_DIR}/venv/bin/python"
if [[ -x "${PYTHON_BIN}" ]]; then
    "${PYTHON_BIN}" -m compileall -q quantbot scripts
    echo "UPDATE_OK commit=$(git rev-parse HEAD)"
else
    echo "UPDATE_OK commit=$(git rev-parse HEAD) (Python validation skipped: venv/bin/python is unavailable)"
fi
