# Sourced by run_trial.sh. CLI pins apply to URLQuery and to any config that sets them;
# configs without pins (the original benchmark) keep the Dockerfile defaults.
has_cli_pins() { [ "$BENCHMARK_ID" = urlquery ] || [ -n "${CFG_CODEX_CLI_VERSION:-}${CFG_CLAUDE_CLI_VERSION:-}" ]; }
resolve_trial_image() {
  IMAGE_BUILD_ARGS=()
  has_cli_pins || return 0
  local version_suffix=""
  if [ -n "${CFG_CODEX_CLI_VERSION:-}" ]; then
    [[ "$CFG_CODEX_CLI_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "codex_cli_version must be an exact numeric version" >&2; return 2; }
    IMAGE_BUILD_ARGS+=(--build-arg "CODEX_VERSION=rust-v$CFG_CODEX_CLI_VERSION")
    version_suffix="-codex-$CFG_CODEX_CLI_VERSION"
  elif [[ "$IMAGE" == *-codex-[0-9]* ]]; then
    echo "versioned Codex image requires a matching config pin" >&2; return 2
  fi
  if [ -n "${CFG_CLAUDE_CLI_VERSION:-}" ]; then
    [[ "$CFG_CLAUDE_CLI_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "claude_cli_version must be an exact numeric version" >&2; return 2; }
    IMAGE_BUILD_ARGS+=(--build-arg "CLAUDE_VERSION=$CFG_CLAUDE_CLI_VERSION")
    version_suffix="$version_suffix-claude-$CFG_CLAUDE_CLI_VERSION"
  elif [[ "$IMAGE" == *-claude-[0-9]* ]]; then
    echo "versioned Claude image requires a matching config pin" >&2; return 2
  fi
  local prefix=mbab-pinned-sandbox
  [ "$BENCHMARK_ID" != urlquery ] || prefix=mbab-urlquery-sandbox
  [ "$IMAGE" != mbab-sandbox ] || IMAGE="$prefix$version_suffix"
  if [ -n "$version_suffix" ] && [[ "$IMAGE" != *"$version_suffix" ]]; then
    echo "pinned image must end with $version_suffix" >&2; return 2
  fi
}

verify_trial_cli_version() {
  has_cli_pins || return 0
  local expected_cli="" cli_line=""
  case "$AGENT" in
    codex) [ -z "${CFG_CODEX_CLI_VERSION:-}" ] || expected_cli="codex-cli $CFG_CODEX_CLI_VERSION" ;;
    claude) [ -z "${CFG_CLAUDE_CLI_VERSION:-}" ] || expected_cli="$CFG_CLAUDE_CLI_VERSION (Claude Code)" ;;
  esac
  [ -n "$expected_cli" ] || return 0
  while IFS= read -r cli_line || [ -n "$cli_line" ]; do
    [ "$cli_line" != "$expected_cli" ] || return 0
  done < "$1"
  echo "CLI version does not match configured pin: expected $expected_cli" >&2
  return 2
}
