# Sourced helper: translate PROVIDER env into codex exec --config flags.
#
# PROVIDER=""         (default) OpenAI gpt via normal codex auth; no extra flags.
# PROVIDER="deepseek" DeepSeek V4 via the local Moon Bridge proxy
#                     (Responses API -> api.deepseek.com translation on
#                     127.0.0.1:38440; systemd unit rethlas-bridge).
#
# Sets: PROVIDER_FLAGS (array). May adjust MODEL if it is still the gpt default.

MOONBRIDGE_URL="${MOONBRIDGE_URL:-http://127.0.0.1:38440/v1}"
MOONBRIDGE_CATALOG="${MOONBRIDGE_CATALOG:-$HOME/moon-bridge/models_catalog.json}"

PROVIDER_FLAGS=()
case "${PROVIDER:-}" in
  "")
    ;;
  deepseek)
    if [[ "${MODEL:-}" == "gpt-5.5" || -z "${MODEL:-}" ]]; then
      MODEL="deepseek-v4-pro"
    fi
    PROVIDER_FLAGS+=(
      --config 'model_providers.moonbridge.name="Moon Bridge"'
      --config "model_providers.moonbridge.base_url=\"$MOONBRIDGE_URL\""
      --config 'model_providers.moonbridge.wire_api="responses"'
      --config 'model_provider="moonbridge"'
      --config "model_catalog_json=\"$MOONBRIDGE_CATALOG\""
      --config 'model_reasoning_summary="detailed"'
    )
    ;;
  *)
    echo "Unknown PROVIDER: ${PROVIDER} (expected empty or 'deepseek')" >&2
    exit 2
    ;;
esac
