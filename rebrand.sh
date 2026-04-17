#!/usr/bin/env bash
# Rebrand local_openai → personality_llm
#
# Idempotent: safe to run multiple times. All sed substitutions are no-ops
# if the old string is already gone. Directory rename only fires when the
# old path exists and the new one does not.
#
# Requirements: GNU sed (standard on Linux / Git Bash on Windows / WSL)
#
# Usage:
#   bash rebrand.sh
#
# Customise the variables below before running.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------

OLD_DOMAIN="local_openai"
NEW_DOMAIN="personality_llm"

OLD_NAME="Local OpenAI LLM"
NEW_NAME="Personality LLM"

# Your GitHub username (used in manifest.json codeowners + HTTP-Referer header)
NEW_GITHUB_USER="Paul-Glavin"

# ---------------------------------------------------------------------------
# Derived values — no need to edit below this line
# ---------------------------------------------------------------------------

UPSTREAM_REPO="https://github.com/skye-harris/hass_local_openai_llm"
NEW_REPO="https://github.com/${NEW_GITHUB_USER}/personality_llm"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPONENTS_DIR="${ROOT_DIR}/custom_components"
OLD_DIR="${COMPONENTS_DIR}/${OLD_DOMAIN}"
NEW_DIR="${COMPONENTS_DIR}/${NEW_DOMAIN}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() { echo "[rebrand] $*"; }

# In-place sed replacement; prints a message only when something changes.
# Usage: replace_in_file "old" "new" "file"
replace_in_file() {
    local old="$1" new="$2" file="$3"
    if grep -qF -- "$old" "$file" 2>/dev/null; then
        sed -i "s|${old}|${new}|g" "$file"
        log "  updated: $(basename "$file")"
    fi
}

# ---------------------------------------------------------------------------
# Step 1 — Rename the component directory
# ---------------------------------------------------------------------------

log "Step 1: rename component directory"

if [ -d "$OLD_DIR" ] && [ ! -d "$NEW_DIR" ]; then
    mv "$OLD_DIR" "$NEW_DIR"
    log "  renamed custom_components/${OLD_DOMAIN}/ → custom_components/${NEW_DOMAIN}/"
elif [ ! -d "$OLD_DIR" ] && [ -d "$NEW_DIR" ]; then
    log "  already renamed, skipping"
elif [ -d "$OLD_DIR" ] && [ -d "$NEW_DIR" ]; then
    echo "[rebrand] ERROR: both ${OLD_DIR} and ${NEW_DIR} exist — resolve manually" >&2
    exit 1
else
    echo "[rebrand] ERROR: neither ${OLD_DIR} nor ${NEW_DIR} exists" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 2 — Python: update DOMAIN constant in const.py
# ---------------------------------------------------------------------------

log "Step 2: update DOMAIN constant and module docstring (const.py)"

CONST_PY="${NEW_DIR}/const.py"
replace_in_file "${OLD_NAME}" "${NEW_NAME}" "$CONST_PY"
replace_in_file \
    "DOMAIN = \"${OLD_DOMAIN}\"" \
    "DOMAIN = \"${NEW_DOMAIN}\"" \
    "$CONST_PY"

# ---------------------------------------------------------------------------
# Step 2b — Python: fix absolute import in weaviate.py
#            (unusual — most files use relative imports, but weaviate.py
#             hardcodes the component path in its LOGGER import)
# ---------------------------------------------------------------------------

log "Step 2b: fix absolute import in weaviate.py"

WEAVIATE_PY="${NEW_DIR}/weaviate.py"
replace_in_file \
    "from custom_components.${OLD_DOMAIN} import" \
    "from custom_components.${NEW_DOMAIN} import" \
    "$WEAVIATE_PY"

# ---------------------------------------------------------------------------
# Step 3 — Python: update HTTP-Referer header in entity.py
#           (sent to OpenRouter for attribution; update to point at this fork)
# ---------------------------------------------------------------------------

log "Step 3: update HTTP-Referer header (entity.py)"

ENTITY_PY="${NEW_DIR}/entity.py"
replace_in_file \
    "\"HTTP-Referer\": \"${UPSTREAM_REPO}\"" \
    "\"HTTP-Referer\": \"${NEW_REPO}\"" \
    "$ENTITY_PY"

# ---------------------------------------------------------------------------
# Step 4 — manifest.json: domain, name, documentation, codeowners
# ---------------------------------------------------------------------------

log "Step 4: update manifest.json"

MANIFEST="${NEW_DIR}/manifest.json"

replace_in_file \
    "\"domain\": \"${OLD_DOMAIN}\"" \
    "\"domain\": \"${NEW_DOMAIN}\"" \
    "$MANIFEST"

replace_in_file \
    "\"name\": \"${OLD_NAME}\"" \
    "\"name\": \"${NEW_NAME}\"" \
    "$MANIFEST"

replace_in_file \
    "\"documentation\": \"${UPSTREAM_REPO}\"" \
    "\"documentation\": \"${NEW_REPO}\"" \
    "$MANIFEST"

replace_in_file \
    "\"@skyeharris\"" \
    "\"@${NEW_GITHUB_USER}\"" \
    "$MANIFEST"

# ---------------------------------------------------------------------------
# Step 5 — translations/en.json: user-facing display strings
# ---------------------------------------------------------------------------

log "Step 5: update translations/en.json"

EN_JSON="${NEW_DIR}/translations/en.json"

replace_in_file "Configure Local OpenAI Server"   "Configure ${NEW_NAME} Server"   "$EN_JSON"
replace_in_file "Reconfigure Local OpenAI Server" "Reconfigure ${NEW_NAME} Server" "$EN_JSON"

# ---------------------------------------------------------------------------
# Step 6 — services.yaml: integration target used for entity filtering
# ---------------------------------------------------------------------------

log "Step 6: update services.yaml"

SERVICES_YAML="${NEW_DIR}/services.yaml"
replace_in_file \
    "integration: ${OLD_DOMAIN}" \
    "integration: ${NEW_DOMAIN}" \
    "$SERVICES_YAML"

# Also update the service description prose that names the integration
replace_in_file \
    "Local AI Agent" \
    "${NEW_NAME} Agent" \
    "$SERVICES_YAML"

# ---------------------------------------------------------------------------
# Step 7 — hacs.json: integration name and zip filename
# ---------------------------------------------------------------------------

log "Step 7: update hacs.json"

HACS_JSON="${ROOT_DIR}/hacs.json"

replace_in_file \
    "\"name\": \"${OLD_NAME}\"" \
    "\"name\": \"${NEW_NAME}\"" \
    "$HACS_JSON"

replace_in_file \
    "\"filename\": \"${OLD_DOMAIN}.zip\"" \
    "\"filename\": \"${NEW_DOMAIN}.zip\"" \
    "$HACS_JSON"

# ---------------------------------------------------------------------------
# Step 8 — GitHub Actions release.yml: folder paths and zip artifact name
# ---------------------------------------------------------------------------

log "Step 8: update .github/workflows/release.yml"

RELEASE_YML="${ROOT_DIR}/.github/workflows/release.yml"

replace_in_file \
    "custom_components/${OLD_DOMAIN}/manifest.json" \
    "custom_components/${NEW_DOMAIN}/manifest.json" \
    "$RELEASE_YML"

replace_in_file \
    "cd \"\${{ github.workspace }}/custom_components/${OLD_DOMAIN}\"" \
    "cd \"\${{ github.workspace }}/custom_components/${NEW_DOMAIN}\"" \
    "$RELEASE_YML"

replace_in_file \
    "zip ${OLD_DOMAIN}.zip" \
    "zip ${NEW_DOMAIN}.zip" \
    "$RELEASE_YML"

replace_in_file \
    "custom_components/${OLD_DOMAIN}/${OLD_DOMAIN}.zip" \
    "custom_components/${NEW_DOMAIN}/${NEW_DOMAIN}.zip" \
    "$RELEASE_YML"

# ---------------------------------------------------------------------------
# Step 9 — .github/ISSUE_TEMPLATE/bug_report.yml: display name references
# ---------------------------------------------------------------------------

log "Step 9: update bug_report.yml"

BUG_REPORT="${ROOT_DIR}/.github/ISSUE_TEMPLATE/bug_report.yml"

replace_in_file "Local OpenAI LLM" "${NEW_NAME}" "$BUG_REPORT"
replace_in_file "${UPSTREAM_REPO}"  "${NEW_REPO}"  "$BUG_REPORT"

# ---------------------------------------------------------------------------
# Step 10 — README.md: fork attribution banner + name + service action ref
# ---------------------------------------------------------------------------

log "Step 10: update README.md"

README="${ROOT_DIR}/README.md"

ATTRIBUTION_MARKER="<!-- personality_llm-fork-attribution -->"

# Add fork attribution banner after the h1 heading, but only once.
# Uses head/tail rather than sed to avoid escaping issues with > characters.
if ! grep -qF "$ATTRIBUTION_MARKER" "$README"; then
    TMPFILE=$(mktemp)
    head -1 "$README" > "$TMPFILE"
    printf '%s\n' \
        "" \
        "$ATTRIBUTION_MARKER" \
        "> **This is a fork of [hass_local_openai_llm](${UPSTREAM_REPO}) by [@skye-harris](https://github.com/skye-harris).**" \
        "> Upstream changes are merged periodically. For issues specific to this fork, open an issue here rather than upstream." \
        "" >> "$TMPFILE"
    tail -n +2 "$README" >> "$TMPFILE"
    mv "$TMPFILE" "$README"
    log "  inserted fork attribution banner"
else
    log "  fork attribution already present, skipping"
fi

# Update integration name in prose
# NOTE: the attribution banner uses "hass_local_openai_llm" (not "${OLD_NAME}")
# so these replacements are safe and won't corrupt the banner.
replace_in_file "# Local OpenAI LLM"   "# ${NEW_NAME}"   "$README"
replace_in_file "${OLD_NAME}"           "${NEW_NAME}"     "$README"

# Update service action name referenced in the RAG section
replace_in_file \
    "${OLD_DOMAIN}.add_to_weaviate" \
    "${NEW_DOMAIN}.add_to_weaviate" \
    "$README"

# HACS badge link (my.home-assistant.io redirect)
replace_in_file \
    "owner=skye-harris&repository=hass_local_openai_llm" \
    "owner=${NEW_GITHUB_USER}&repository=personality_llm" \
    "$README"

# HACS manual install note — "add `<url>` as a custom repository"
replace_in_file \
    "add \`${UPSTREAM_REPO}\` as a custom repository" \
    "add \`${NEW_REPO}\` as a custom repository" \
    "$README"

# Manual install "latest release" download link
replace_in_file \
    "(${UPSTREAM_REPO}/releases/latest)" \
    "(${NEW_REPO}/releases/latest)" \
    "$README"

# Manual install copy path
replace_in_file \
    "Copy the \`${OLD_DOMAIN}\`" \
    "Copy the \`${NEW_DOMAIN}\`" \
    "$README"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

log ""
log "Rebrand complete."
log ""
log "Summary of changes:"
log "  • custom_components/${OLD_DOMAIN}/ → custom_components/${NEW_DOMAIN}/"
log "  • DOMAIN constant: \"${OLD_DOMAIN}\" → \"${NEW_DOMAIN}\""
log "  • Display name: \"${OLD_NAME}\" → \"${NEW_NAME}\""
log "  • Documentation/repo URLs updated to ${NEW_REPO}"
log "  • Codeowner updated to @${NEW_GITHUB_USER}"
log ""
log "Next steps:"
log "  1. Remove the upstream integration from HA (Settings → Devices & Services)"
log "  2. Restart HA"
log "  3. Copy custom_components/${NEW_DOMAIN}/ to your HA config directory"
log "  4. Restart HA and re-add the integration (it will appear as '${NEW_NAME}')"
log "  5. Run: git diff  — to review all changes before committing"
