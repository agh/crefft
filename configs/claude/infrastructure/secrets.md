# Agent Secrets Management

> [crefft](../../../README.md) > [Agent Infrastructure](README.md) > Secrets

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and
"OPTIONAL" in this document are to be interpreted as described in
BCP 14 [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119)
[RFC 8174](https://datatracker.ietf.org/doc/html/rfc8174) when, and only
when, they appear in all capitals, as shown here.

## Security Boundary

Decrypted values **MUST NOT** reach terminal stdout, stderr, logs, prompts, agent
transcripts, recordings, test output, plaintext files, caches, or other artifacts.
They **MUST NOT** enter an environment wider than the one trusted process that
needs them. Failed decryption, a missing key, or a missing file **MUST** stop
execution before that process starts.

**Why**: terminal output and environment inheritance copy a credential into places
that outlive the operation or are visible to unrelated tools.

Agents **MUST NOT** receive credentials that can publish or push, including GitHub
write tokens, registry credentials, deployment keys, or SSH-agent access with
those permissions. Tasks requiring them **MUST** run as a separate, human-approved
step outside the agent.

**Why**: approval of a plan does not constrain what an agent or its next tool can
do with an inherited credential.

An agent **MUST NOT** have access to decryption identities, a general-purpose
secret-returning MCP tool, or a configurable secret launcher. A human-controlled
supervisor **MUST** fix the encrypted file, allowed keys, and trusted executable
outside the agent's writable workspace. It **MUST** return only approved,
non-sensitive results, never a credential.

**Why**: a launcher accepting an agent-selected command can be turned into a
secret-printing command even if its default command is safe.

```text
Encrypted file + protected age identity
                  |
        Human-controlled supervisor
                  |
       Pinned SOPS -> private pipe -> scoped helper
                                         |
                           Two named keys, one trusted child
                                         |
                             Approved result, no secret

Agent: no identity, no credential environment, no publishing permission
```

## Pinned Tools

This pattern uses **SOPS 3.13.3**, **age 1.3.2**, and Python 3's standard library
on POSIX systems with `/dev/fd/`. The pin and extraction behavior were verified
against the [SOPS 3.13.3 release](https://github.com/getsops/sops/releases/tag/v3.13.3),
its [decryption implementation](https://github.com/getsops/sops/blob/v3.13.3/cmd/sops/decrypt.go),
and local synthetic-fixture tests on macOS arm64 with those tool versions.
The executable helper rejects any other SOPS version.

Operators **MUST** obtain the pinned binaries from their official releases,
verify their checksums and signatures using the release instructions, and keep
their absolute paths and parent directories outside agent write access.
See the [age 1.3.2 release](https://github.com/FiloSottile/age/releases/tag/v1.3.2).

**Why**: a version string alone does not authenticate an executable, and a
substituted executable could disclose the identity or decrypted values.

## Create Encrypted Secrets

A human-controlled provisioning system **MUST** create and update the encrypted
file outside the agent. Its plaintext input **MUST** travel through a private,
inherited pipe or file descriptor, not a terminal, shell argument, environment
variable, editor recovery file, or saved plaintext file. Only encrypted output
belongs in the repository.

**Why**: encrypting a file afterward does not remove copies already captured by
an editor, shell history, an agent transcript, or a backup.

Use a separate age identity and encrypted file per purpose and environment. The
following is a structural illustration, not usable ciphertext:

```yaml
# secrets.yaml: only read-only database access belongs in this file.
postgres_readonly:
  POSTGRES_USER: ENC[...]
  POSTGRES_PASSWORD: ENC[...]
sops:
  # SOPS writes the age recipients, encrypted data key, MAC, and version here.
```

The role **MUST** be read-only at the database, not just named "readonly." The
`postgres_readonly` branch **MUST** contain exactly the two nonempty string keys
shown above; the helper rejects missing keys, extra keys, nonstrings, and NULs.

**Why**: fixed names and server-enforced permissions prevent a renamed write
credential or an unexpected environment variable from expanding access.

## One Scoped Execution Pattern

Use [sops_command.py](sops_command.py) only from the protected supervisor. Its
policy selects `["postgres_readonly"]` and requires exactly `POSTGRES_USER` and
`POSTGRES_PASSWORD`. SOPS verifies the entire document internally before
extracting that branch; no other branch crosses the private pipe or enters the
child's environment. Separate encrypted files and identities remain the
cryptographic isolation boundary.

The helper invokes SOPS with `decrypt`, `--extract`, `--output-type json`, and
`--output /dev/fd/<private-pipe>`. SOPS stdout and stderr are discarded; decrypted
bytes use only the private descriptor of an unlinked FIFO in a mode-`0700`
temporary directory. No regular plaintext file is created. The helper reads and
validates the complete result and SOPS exit status before launching anything.
It never modifies its own or its parent's environment.

### Check Without Revealing a Value

From the repository root, with `SOPS_BIN`, `AGE_IDENTITY`, and `SECRETS_FILE`
holding absolute, non-sensitive paths:

```bash
python3 configs/claude/infrastructure/sops_command.py \
  --sops "$SOPS_BIN" --identity "$AGE_IDENTITY" --file "$SECRETS_FILE" --check
```

Success prints only two labeled byte lengths:

```text
POSTGRES_USER: length=<byte-count> bytes
POSTGRES_PASSWORD: length=<byte-count> bytes
```

An operator **MUST** compare these lengths with the expected lengths privately.
The check proves authenticated decryption and the required shape, not that a
password is correct. Lengths **MUST NOT** be archived when they are sensitive.

**Why**: a length check reveals no plaintext, whereas printing a value for
debugging sends it to scrollback and transcripts. Even a digest can enable
offline guessing of a low-entropy password.

### Run Only the Trusted Consumer

The supervisor runs one reviewed, absolute executable, not an agent, shell, or
general-purpose MCP server:

```bash
python3 configs/claude/infrastructure/sops_command.py \
  --sops "$SOPS_BIN" --identity "$AGE_IDENTITY" --file "$SECRETS_FILE" \
  -- /usr/local/libexec/postgres-readonly-check
```

The helper constructs the child's environment from exactly `POSTGRES_USER`,
`POSTGRES_PASSWORD`, and the fixed, non-secret locale `LC_ALL=C`. It forwards no
inherited `HOME`, `PATH`, GitHub token, age identity path, or unrelated secret.
The OS or runtime can add its own non-secret bookkeeping variables at startup.
Arguments are passed without a shell. Child stdin, stdout, and stderr are disconnected;
both output streams go to `/dev/null`. Core dumps are disabled for the helper,
SOPS, and the consumer.

The consumer **MUST NOT** spawn other processes, log credentials, write plaintext
artifacts, or return credentials through another channel. Any additional runtime
configuration **MUST** be fixed and reviewed, not copied from the agent's
environment. The helper and consumer **MUST** remain outside agent write access.

**Why**: a child can otherwise forward its environment or disclose credentials
through files, network calls, or application logs despite protected output.

Don't: launch a general agent with secret environment variables, expose a
`secrets.get` tool, print a decrypted value, forward an SSH agent, or decrypt a
private key to a temporary file.

Do: keep the identity with the supervisor and give only the read-only consumer
the two named keys for the duration of one operation.

### Failure Contract

Every helper failure exits nonzero and prints only this fixed stderr message:

```text
Secret operation failed.
```

Decryption errors, missing files, missing identities, missing keys, invalid
shapes, unsupported SOPS versions, and failed child commands **MUST NOT** be
replaced with empty values or followed by a retry that runs the child anyway.
Raw SOPS and child diagnostics **MUST NOT** be forwarded.

**Why**: diagnostics can include document content, paths, or ciphertext fragments;
a fixed message reports failure without disclosing them.

## Rotation, Audit, and CI

Operators **MUST** retain the old recipient until the `--check` command succeeds
using the new identity. They **MUST** rotate the actual credential as well as the
recipient and repeat the check before retiring old access.

**Why**: changing the encryption recipient does not revoke a copied credential,
and retiring an unverified identity can make the sealed file unreadable.

Audit records **MUST** contain only an approved operation identifier, timestamp,
and success/failure status. CI **MUST** use the same supervisor boundary and
separate, human-approved publishing step, not an agent job with write credentials.

**Why**: logging commands, environments, decrypted content, or raw errors defeats
sealing, and a broad CI environment recreates the original inheritance problem.

## Regression Tests

```bash
python3 -m unittest discover -s scripts -p 'test_secrets_security.py' -v
```

The tests execute the documented helper commands using a temporary age identity
and synthetic SOPS-encrypted YAML, never a real credential. They check selected
keys, parent isolation, value-free output, byte lengths, and fail-closed behavior.
They skip with a clear reason when the pinned SOPS binary, `age`, or `age-keygen`
is unavailable. `SOPS_BIN`, `AGE_BIN`, and `AGE_KEYGEN_BIN` can select local pinned
binaries, including binaries in `.tmp-check/`, without a global installation.
