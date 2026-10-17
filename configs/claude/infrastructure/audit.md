# Agent Audit Logging

Comprehensive logging of all agent actions for compliance, debugging, and
learning.

## Overview

Every agent action **MUST** be logged as metadata, never as copied input,
output, error text, or decision prose.

**Why**: audit destinations are additional disclosure boundaries; a useful
execution trail does not require commands, query text, or returned content.

```text
+---------------------------------------------------------------------------+
|                          AUDIT LOGGING                                    |
+---------------------------------------------------------------------------+
|                                                                           |
|   WHAT TO LOG                                                             |
|   -----------                                                             |
|   - Tool invocations (read, write, bash, etc.)                            |
|   - Skill usage (postgres queries, github API calls)                      |
|   - External calls (web search, web fetch)                                |
|   - Decision identifiers and selected action                              |
|   - Outcome status and duration                                          |
|   - Failure status, without exception or error text                        |
|                                                                           |
|   WHY LOG                                                                 |
|   -------                                                                 |
|   - Compliance & audit trails                                             |
|   - Debugging agent behavior                                              |
|   - Learning from outcomes (train better agents)                          |
|   - Cost tracking (API calls, tokens used)                                |
|   - Security monitoring (detect anomalies)                                |
|                                                                           |
+---------------------------------------------------------------------------+
```

## Log Schema

### Standard Log Entry

This is a metadata schema for multiple producers, not the hook's wire format.
The hook emits only the exact allowlist in [Data Minimization](#data-minimization).
Other producers **MUST** define their own metadata allowlists before adding
fields; generic JSON storage is not permission to copy arbitrary content.

**Why**: tool parameters and summarized results can contain the same secrets
as the original content.

```yaml
log_entry:
  # Identity
  id: uuid
  timestamp: iso8601

  # Agent context
  agent:
    id: "ops/release-manager"
    session_id: uuid
    conversation_id: uuid  # Links to user conversation

  # Action details
  action:
    type: "tool" | "skill" | "external" | "decision" | "error"
    name: string

    # For tool invocations
    tool:
      name: "Bash" | "Read" | "Write" | "Edit" | "Grep" | etc.
      tool_use_id: uuid

    # For skill usage
    skill:
      name: "postgres" | "github" | "discord" | etc.
      operation: string
      request_id: uuid

    # For external calls
    external:
      type: "web_search" | "web_fetch" | "api_call"
      request_id: uuid

    # For decisions
    decision:
      policy_id: string
      options_considered:
        - option: string
          score: float
      chosen: string
      confidence: float

  # Outcome
  outcome:
    status: "success" | "failure" | "partial"
    result:
      # Explicitly allowlisted numeric counts only, never content or excerpts
    error:
      type: string  # Fixed classification code, never exception text

  # Resource usage
  resources:
    tokens_input: int
    tokens_output: int
    duration_ms: int
    cost_usd: float  # Estimated

  # Security context
  security:
    permission_level: "readonly" | "read-write" | "admin"
    resources_accessed:
      - type: string  # Resource class only; no paths, URLs, or query text
    sensitive_data_accessed: boolean
```

### Examples

#### Tool Invocation

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-01-02T10:30:15.123Z",
  "agent": {
    "id": "ops/release-manager",
    "session_id": "abc123",
    "conversation_id": "user-conv-456"
  },
  "action": {
    "type": "tool",
    "name": "Bash",
    "tool": {
      "name": "Bash",
      "tool_use_id": "tool-123"
    }
  },
  "outcome": {
    "status": "success",
    "result": {
      "exit_code": 0,
      "output_lines": 10
    }
  },
  "resources": {
    "duration_ms": 234
  },
  "security": {
    "permission_level": "readonly",
    "resources_accessed": [
      {"type": "git_repository"}
    ]
  }
}
```

#### Skill Usage

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2025-01-02T10:30:20.456Z",
  "agent": {
    "id": "ops/release-manager",
    "session_id": "abc123",
    "conversation_id": "user-conv-456"
  },
  "action": {
    "type": "skill",
    "name": "postgres",
    "skill": {
      "name": "postgres",
      "operation": "query",
      "request_id": "request-123"
    }
  },
  "outcome": {
    "status": "success",
    "result": {
      "rows_returned": 10,
      "execution_time_ms": 45
    }
  },
  "resources": {
    "duration_ms": 52
  },
  "security": {
    "permission_level": "readonly",
    "resources_accessed": [
      {"type": "database_table"}
    ],
    "sensitive_data_accessed": false
  }
}
```

#### Web Search

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "timestamp": "2025-01-02T10:30:25.789Z",
  "agent": {
    "id": "ops/release-manager",
    "session_id": "abc123",
    "conversation_id": "user-conv-456"
  },
  "action": {
    "type": "external",
    "name": "web_search",
    "external": {
      "type": "web_search",
      "request_id": "request-456"
    }
  },
  "outcome": {
    "status": "success",
    "result": {
      "results_returned": 10
    }
  },
  "resources": {
    "duration_ms": 1234,
    "cost_usd": 0.001
  },
  "security": {
    "permission_level": "readonly"
  }
}
```

#### Decision

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440003",
  "timestamp": "2025-01-02T10:31:00.000Z",
  "agent": {
    "id": "ops/rollback-advisor",
    "session_id": "abc123",
    "conversation_id": "user-conv-456"
  },
  "action": {
    "type": "decision",
    "name": "rollback_recommendation",
    "decision": {
      "policy_id": "rollback-readiness",
      "options_considered": [
        {
          "option": "rollback",
          "score": 0.85
        },
        {
          "option": "hotfix",
          "score": 0.60
        },
        {
          "option": "monitor",
          "score": 0.20
        }
      ],
      "chosen": "rollback",
      "confidence": 0.85
    }
  },
  "outcome": {
    "status": "success"
  }
}
```

## Log Destinations

### Local File (Development)

```yaml
audit:
  destination: file
  path: /var/log/agent-audit/
  rotation:
    max_size: 100MB
    max_age: 30d
    compress: true
```

### VictoriaLogs (Production)

```yaml
audit:
  destination: victorialogs
  url: ${VICTORIALOGS_URL}
  stream: agent-audit

  # Structured logging
  format: json

  # Add standard labels
  labels:
    environment: production
    cluster: main
```

### PostgreSQL (Queryable)

```sql
CREATE TABLE agent_audit_log (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Agent identity
  agent_id VARCHAR(100) NOT NULL,
  session_id UUID,
  conversation_id UUID,

  -- Action
  action_type VARCHAR(50) NOT NULL,
  action_name VARCHAR(100) NOT NULL,
  action_details JSONB NOT NULL,

  -- Outcome
  outcome_status VARCHAR(20) NOT NULL,
  outcome_result JSONB,
  outcome_error JSONB,

  -- Resources
  tokens_input INT,
  tokens_output INT,
  duration_ms INT,
  cost_usd DECIMAL(10, 6),

  -- Security
  permission_level VARCHAR(20),
  resources_accessed JSONB,
  sensitive_data_accessed BOOLEAN NOT NULL DEFAULT FALSE,

  -- A unique constraint on a partitioned table MUST contain every
  -- partition-key column, so the key is (id, timestamp), not id alone
  PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Indexes are separate statements in PostgreSQL. Created on the partitioned
-- parent, they propagate to every current and future partition.
CREATE INDEX agent_audit_log_agent_id_idx ON agent_audit_log (agent_id);
CREATE INDEX agent_audit_log_timestamp_idx ON agent_audit_log (timestamp DESC);
CREATE INDEX agent_audit_log_action_type_idx ON agent_audit_log (action_type);
CREATE INDEX agent_audit_log_session_id_idx ON agent_audit_log (session_id);

-- Partition by month for retention
CREATE TABLE agent_audit_log_2026_09 PARTITION OF agent_audit_log
  FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

-- A default partition keeps an out-of-range insert from being rejected
CREATE TABLE agent_audit_log_default PARTITION OF agent_audit_log DEFAULT;
```

Agents **MUST NOT** apply audit DDL straight to production. Apply it to a
disposable database first, on the PostgreSQL version you run:

```bash
docker run -d --name audit-schema-test -e POSTGRES_PASSWORD=test postgres:18
docker exec -i audit-schema-test psql -U postgres -v ON_ERROR_STOP=1 \
  < audit-schema.sql
docker rm -f audit-schema-test
```

**Why**: MySQL-style inline `INDEX` clauses are not valid PostgreSQL, a
`PARTITION OF` clause needs a parent declared `PARTITION BY`, and PostgreSQL
rejects a primary key that omits a partition-key column. All three fail at
`CREATE TABLE` time, so a migration test catches them before deployment.

## Querying Audit Logs

### Recent Activity by Agent

```sql
SELECT
  action_type,
  action_name,
  outcome_status,
  timestamp
FROM agent_audit_log
WHERE agent_id = 'ops/release-manager'
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;
```

### Failed Actions

```sql
SELECT
  agent_id,
  action_name,
  outcome_error,
  timestamp
FROM agent_audit_log
WHERE outcome_status = 'failure'
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;
```

### Cost Analysis

```sql
SELECT
  agent_id,
  DATE_TRUNC('day', timestamp) as day,
  SUM(cost_usd) as total_cost,
  SUM(tokens_input + tokens_output) as total_tokens,
  COUNT(*) as action_count
FROM agent_audit_log
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY agent_id, DATE_TRUNC('day', timestamp)
ORDER BY day DESC, total_cost DESC;
```

### Security Audit

```sql
SELECT
  agent_id,
  action_name,
  resources_accessed,
  timestamp
FROM agent_audit_log
WHERE sensitive_data_accessed = TRUE
  AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;
```

### Learning: Action Outcomes

```sql
-- Which actions succeed vs fail?
SELECT
  agent_id,
  action_name,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE outcome_status = 'success') as successes,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE outcome_status = 'success') / COUNT(*),
    1
  ) as success_rate
FROM agent_audit_log
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY agent_id, action_name
HAVING COUNT(*) > 10
ORDER BY success_rate ASC;
```

## Integration with Claude Code

### Hook-Based Logging

Claude Code fires `PostToolUse` after a tool succeeds and `PostToolUseFailure`
after a tool fails. Both take an array of matcher groups; each group holds an
array of handlers. Register the same logger on both events:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/agent-audit-log",
            "args": [],
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/agent-audit-log",
            "args": [],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Why**: `PostToolCall` is not a Claude Code event, and an object where an
array is expected is discarded, so the hook never runs. `timeout` is in
seconds, not milliseconds. Setting `args` selects exec form, which substitutes
`${CLAUDE_PROJECT_DIR}` into `command` without shell quoting.

The handler reads one JSON object on stdin. `PostToolUse` supplies
`tool_response`; `PostToolUseFailure` supplies `error` instead, so the outcome
**MUST** be derived from `hook_event_name` rather than hard-coded. Install the
executable [metadata-only hook](audit-hook.sh) from the repository root:

```bash
mkdir -p .claude/hooks
install -m 755 configs/claude/infrastructure/audit-hook.sh .claude/hooks/agent-audit-log
```

The hook requires Bash, `jq`, `curl`, and `AUDIT_LOG_URL` in its environment.
It **MUST** send only the allowlisted metadata described in
[Data Minimization](#data-minimization), never tool input, output, or errors.

**Why**: commands, query results, and error messages can all carry credentials.
Redacting known patterns or truncating text cannot prevent content disclosure.

A failed POST exits 1, which Claude Code reports as a non-blocking hook error
instead of silently dropping the record. Invalid events also exit 1 with a
fixed diagnostic that contains no event content. All delivery failures,
including `curl` exit 2, are mapped to 1: only exit code 2 blocks, and a
`PostToolUse` hook **MUST NOT** block for a logging failure after the tool ran.
The request has a four-second deadline, and response bodies are discarded.

### Validating Hook Configuration in CI

`claude doctor` reports rejected settings but still exits 0, so CI **MUST**
fail on the report text rather than on the exit status:

```bash
#!/usr/bin/env bash
# ci-check-claude-settings - fail the build on settings Claude Code rejects
set -euo pipefail

report=$(claude doctor 2>&1)
printf '%s\n' "$report"

if printf '%s\n' "$report" | grep -q '^Invalid settings'; then
  echo "Claude Code rejected part of the settings above" >&2
  exit 1
fi
```

### MCP Server for Audit

```json
{
  "mcpServers": {
    "audit": {
      "command": "mcp-audit-logger",
      "env": {
        "AUDIT_BACKEND": "postgres",
        "AUDIT_DATABASE_URL": "${AUDIT_DATABASE_URL}",
        "AGENT_ID": "${AGENT_ID}"
      }
    }
  }
}
```

## Privacy Considerations

### Data Minimization

The [hook](audit-hook.sh) constructs a new JSON object with exactly these fields;
this is its implemented policy, not a separate YAML setting:

| Field | Source |
| ----- | ------ |
| `timestamp` | Hook-generated UTC timestamp |
| `hook_event_name` | `PostToolUse` or `PostToolUseFailure` |
| `agent.session_id` | Session identifier |
| `action.type` | Constant `tool` |
| `action.name` | Tool name |
| `action.tool_use_id` | Tool invocation identifier |
| `outcome.status` | `success` or `failure`, derived from the event name |
| `outcome.duration_ms` | Nonnegative numeric duration, or `null` when absent |

Identifiers **MUST** be 1-256 ASCII letters, digits, underscores, periods,
colons, or hyphens. Unknown events and malformed metadata are rejected before
any POST. The hook omits working directories, paths, permission modes, input,
output, error text, and every unrecognized field. It does not truncate,
redact, hash, or copy content.

**Why**: an allowlist remains safe when event schemas gain new fields; a
denylist can forward a new secret-bearing field without any code change.

```text
Do:    record tool name, invocation ID, outcome status, and duration
Don't: record a command, a result row, an error message, or a content excerpt
```

### Retention Policy

```yaml
audit:
  retention:
    hot: 7d      # Complete metadata records, fast queries
    warm: 30d    # Aggregated, slower queries
    cold: 365d   # Archived, compliance only

  # Auto-delete PII after period
  pii_retention: 30d
```

## Alerting on Audit Events

```yaml
alerts:
  # Alert on sensitive data access
  - name: sensitive_data_accessed
    condition: |
      agent_audit_log
      | sensitive_data_accessed = true
      | count() > 0
    window: 5m
    action: notify_security

  # Alert on high failure rate
  - name: agent_failure_spike
    condition: |
      agent_audit_log
      | outcome_status = 'failure'
      | count() by agent_id
      | count > 10
    window: 15m
    action: notify_ops

  # Alert on unusual activity
  - name: unusual_agent_activity
    condition: |
      agent_audit_log
      | count() by agent_id
      | count > avg(count) * 3
    window: 1h
    action: notify_security
```
