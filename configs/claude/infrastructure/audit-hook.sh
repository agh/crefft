#!/usr/bin/env bash
set -euo pipefail

if [ -z "${AUDIT_LOG_URL:-}" ]; then
  printf '%s\n' 'audit hook: AUDIT_LOG_URL is required' >&2
  exit 1
fi

# Build the entire record before posting; never forward the source event.
if ! payload=$(jq -ces '
  def identifier:
    type == "string" and length > 0 and length <= 256
    and test("^[A-Za-z0-9_.:-]+$");
  if length != 1 then error("expected one event") else .[0] end
  | if type != "object" then error("expected an object") else . end
  | if (.hook_event_name != "PostToolUse" and .hook_event_name != "PostToolUseFailure")
       or (.session_id | identifier | not)
       or (.tool_name | identifier | not)
       or (.tool_use_id | identifier | not)
    then error("invalid event metadata") else . end
  | {
      timestamp: (now | todate),
      hook_event_name: .hook_event_name,
      agent: {session_id: .session_id},
      action: {type: "tool", name: .tool_name, tool_use_id: .tool_use_id},
      outcome: {
        status: (if .hook_event_name == "PostToolUse" then "success" else "failure" end),
        duration_ms: (
          .duration_ms
          | if . == null or (type == "number" and . >= 0)
            then . else error("invalid duration") end
        )
      }
    }
' 2>/dev/null); then
  printf '%s\n' 'audit hook: invalid event; nothing posted' >&2
  exit 1
fi

if ! curl --silent --show-error --fail --max-time 4 --output /dev/null \
  -X POST "${AUDIT_LOG_URL%/}/log" \
  -H 'Content-Type: application/json' --data-binary @- <<<"$payload"; then
  printf '%s\n' 'audit hook: metadata delivery failed' >&2
  exit 1
fi
