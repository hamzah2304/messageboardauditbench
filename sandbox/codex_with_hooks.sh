#!/bin/sh
# Inspect SWE exposes arbitrary Codex config overrides but not arbitrary CLI
# flags. This benchmark image is already externally isolated, so enable its
# vetted lifecycle hooks without interactive trust prompts.
if [ "${1:-}" = exec ]; then
  shift
  exec /usr/local/bin/codex-real exec --dangerously-bypass-hook-trust "$@"
fi
exec /usr/local/bin/codex-real "$@"
