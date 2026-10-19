# crefft — local checks
#
# `make check` runs the same checks as .forgejo/workflows/doc-lint.yml, in the
# same order and with the same pinned tool versions, so a green local run
# means a green CI run.
#
# Requirements: Node.js 24+, Python 3.14+, curl, tar. Everything else is
# fetched at a pinned version into .tmp-check/.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

NODE_BIN := node_modules/.bin
TMP := .tmp-check

# Pinned to match .forgejo/workflows/doc-lint.yml.
GITLEAKS_VERSION := 8.30.1
GITLEAKS_SHA256_darwin_arm64 := b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5
GITLEAKS_SHA256_linux_x64 := 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_S),Darwin)
  ifeq ($(UNAME_M),arm64)
    GITLEAKS_PLATFORM := darwin_arm64
  else
    GITLEAKS_PLATFORM := darwin_x64
  endif
else
  ifeq ($(UNAME_M),aarch64)
    GITLEAKS_PLATFORM := linux_arm64
  else
    GITLEAKS_PLATFORM := linux_x64
  endif
endif
GITLEAKS_SHA256 := $(GITLEAKS_SHA256_$(GITLEAKS_PLATFORM))
GITLEAKS_ARCHIVE := gitleaks_$(GITLEAKS_VERSION)_$(GITLEAKS_PLATFORM).tar.gz
GITLEAKS := $(TMP)/gitleaks

# Release asset SHA-256 digests from crate-ci/typos v1.51.1 on GitHub.
TYPOS_VERSION := 1.51.1
TYPOS_PLATFORM_Darwin_arm64 := aarch64-apple-darwin
TYPOS_PLATFORM_Darwin_x86_64 := x86_64-apple-darwin
TYPOS_PLATFORM_Linux_aarch64 := aarch64-unknown-linux-musl
TYPOS_PLATFORM_Linux_x86_64 := x86_64-unknown-linux-musl
TYPOS_PLATFORM := $(TYPOS_PLATFORM_$(UNAME_S)_$(UNAME_M))
TYPOS_SHA256_aarch64-apple-darwin := \
  316d50a32c3726a80ab39c6d12141b70080498973c5e8a9b068b12cde78b10c1
TYPOS_SHA256_x86_64-apple-darwin := \
  f3451079971633a7f769fb958fe06b0d64b5f1dc46df0854aa1ddb9a6f4031d6
TYPOS_SHA256_aarch64-unknown-linux-musl := \
  2ac5e37b3236b3c07dec5cdf1527acf143aec4674a6089b0bf424d021b35e099
TYPOS_SHA256_x86_64-unknown-linux-musl := \
  93c301fd4120ff076e2cc2a6d6a61cab4a4bdb81899287c0938b452e56d1f454
TYPOS_SHA256 := $(TYPOS_SHA256_$(TYPOS_PLATFORM))
TYPOS_ARCHIVE := typos-v$(TYPOS_VERSION)-$(TYPOS_PLATFORM).tar.gz
TYPOS := $(TMP)/typos-$(TYPOS_VERSION)/typos

# Release asset digests from vale_3.24.0_checksums.txt.
VALE_VERSION := 3.24.0
VALE_PLATFORM_Darwin_arm64 := macOS_arm64
VALE_PLATFORM_Darwin_x86_64 := macOS_64-bit
VALE_PLATFORM_Linux_aarch64 := Linux_arm64
VALE_PLATFORM_Linux_x86_64 := Linux_64-bit
VALE_PLATFORM := $(VALE_PLATFORM_$(UNAME_S)_$(UNAME_M))
VALE_SHA256_macOS_arm64 := \
  87b513f26499f6657c15cf7175ba5b058a7c1ff2bb2d4e07265db2dd43451e44
VALE_SHA256_macOS_64-bit := \
  eeb39e86f1daac27cc2a77fef3af1824d50559bdc22329fb25fb921c80c79472
VALE_SHA256_Linux_arm64 := \
  104cbd349279e50c4cb40adb70adf345d93cc4a3a0191f9e68bdccb97086b582
VALE_SHA256_Linux_64-bit := \
  867534ddb678abca7f214bc4706ead0922bd5252ffe8035fc227013f66c8b214
VALE_SHA256 := $(VALE_SHA256_$(VALE_PLATFORM))
VALE_ARCHIVE := vale_$(VALE_VERSION)_$(VALE_PLATFORM).tar.gz
VALE := $(TMP)/vale-$(VALE_VERSION)/vale
VALE_PACKAGE_DIR := $(TMP)/vale-package

# Include new files and omit deleted paths while checking an uncommitted move.
MARKDOWN_FILES = $(wildcard $(shell git ls-files --cached --others \
	--exclude-standard --deduplicate '*.md' ':!:reference/**'))

# Generates a deliberately realistic pair of tokens for the Gitleaks
# self-test. Built at run time so no credential-shaped literal is committed.
define GITLEAKS_FIXTURE_PY
import secrets
import string
import sys

ALNUM = string.ascii_letters + string.digits


def token(length):
    return "".join(secrets.choice(ALNUM) for _ in range(length))


with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write('const githubToken = "ghp_%s";\n' % token(36))
    handle.write('const stripeKey = "sk_live_%s";\n' % token(24))
endef
export GITLEAKS_FIXTURE_PY

.DEFAULT_GOAL := help
.PHONY: site-check publish-release

site-check: ## Build and check the static website (install with npm ci --prefix site)
	npm --prefix site run verify

publish-release: export RELEASE_TAG = $(TAG)
publish-release: ## Verify a signed forge release and print its GitHub push (TAG=vYYYY.M.N)
	@python3 scripts/publish_release.py --tag "$$RELEASE_TAG"

.PHONY: help check install lint typos vale vale-package vale-package-check links links-external secrets versions snippets test clean

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

check: lint typos vale links secrets versions vendored snippets ## Run every check CI runs

install: node_modules ## Install the pinned documentation toolchain

node_modules: package.json package-lock.json
	npm ci
	@touch node_modules

lint: install ## Lint Markdown with markdownlint-cli2
	$(NODE_BIN)/markdownlint-cli2 $(MARKDOWN_FILES) site/README.md SITE-CHANGELOG.md

typos: $(TYPOS) ## Enforce US spelling in first-party code and prose
	$(TYPOS) --version
	$(TYPOS) --config _typos.toml .

vale: $(VALE) vale-package-check ## Enforce the Crefft writing rules in tracked Markdown
	$(VALE) --no-global --version
	$(VALE) --no-global sync
	$(VALE) --no-global test --coverage configs/vale/Crefft/styles/Crefft
	@printf '%s\0' $(MARKDOWN_FILES) | xargs -0 $(VALE) --no-global

vale-package: ## Build the deterministic Crefft archive and checksum
	python3 scripts/build_vale_package.py --output-dir $(VALE_PACKAGE_DIR)

vale-package-check: $(VALE) vale-package ## Sync and exercise the built archive as a consumer
	python3 scripts/check_vale_package.py --vale $(VALE) \
	  --package $(VALE_PACKAGE_DIR)/Crefft.zip

links: install ## Check internal links in all first-party Markdown (blocking)
	@printf '%s\0' $(MARKDOWN_FILES) \
	  | xargs -0 $(NODE_BIN)/markdown-link-check \
	      --config .markdown-link-check-internal.json --quiet

links-external: install ## Check external URLs (what CI runs weekly; network-bound)
	@set -uo pipefail; \
	report=$$(mktemp); \
	printf '%s\0' $(MARKDOWN_FILES) \
	  | xargs -0 -P 4 -I{} sh -c '$(NODE_BIN)/markdown-link-check \
	      --config .markdown-link-check.json --quiet "$$1" 2>&1 \
	      || echo "FAILED: $$1"' _ {} >> "$$report" 2>&1 || true; \
	grep -E '^(FAILED: |ERROR:|[[:space:]]+\[)' "$$report" || true; \
	failed=$$(grep -c '^FAILED: ' "$$report" || true); \
	rm -f "$$report"; \
	echo "$$failed file(s) contain unreachable external URLs"

secrets: $(GITLEAKS) ## Scan for secrets, and prove the allowlist still bites
	@rm -rf $(TMP)/gitleaks-fixture
	@mkdir -p $(TMP)/gitleaks-fixture
	@python3 -c "$$GITLEAKS_FIXTURE_PY" $(TMP)/gitleaks-fixture/leak.js
	@if $(GITLEAKS) dir $(TMP)/gitleaks-fixture --config site/gitleaks.toml \
	      --no-banner --redact >/dev/null 2>&1; then \
	  rm -rf $(TMP)/gitleaks-fixture; \
	  echo "FAIL: .gitleaks.toml no longer detects a realistic token"; exit 1; \
	else \
	  rm -rf $(TMP)/gitleaks-fixture; \
	  echo "self-test passed: realistic tokens are still detected"; \
	fi
	$(GITLEAKS) dir . --config site/gitleaks.toml --no-banner --redact --verbose

versions: test ## Check canonical versions, action SHAs, and image pins
	python3 scripts/validate_versions.py

test: ## Run the script unit tests
	python3 -m unittest discover scripts

snippets: install ## Syntax-check fenced code blocks (advisory)
	python3 scripts/check_snippets.py --warn

$(GITLEAKS):
	@mkdir -p $(TMP)
	curl --fail-with-body --location --silent --show-error --retry 3 \
	  --output $(TMP)/gitleaks.tar.gz \
	  "https://github.com/gitleaks/gitleaks/releases/download/v$(GITLEAKS_VERSION)/$(GITLEAKS_ARCHIVE)"
	@echo "$(GITLEAKS_SHA256)  $(TMP)/gitleaks.tar.gz" | shasum -a 256 -c -
	tar -xzf $(TMP)/gitleaks.tar.gz -C $(TMP) gitleaks
	@rm -f $(TMP)/gitleaks.tar.gz

$(TYPOS):
	@test -n "$(TYPOS_SHA256)" || { echo "Unsupported typos platform: $(UNAME_S)/$(UNAME_M)"; exit 1; }
	@mkdir -p $(TMP)/typos-$(TYPOS_VERSION)
	curl --fail-with-body --location --silent --show-error --retry 3 \
	  --output $(TMP)/$(TYPOS_ARCHIVE) \
	  "https://github.com/crate-ci/typos/releases/download/v$(TYPOS_VERSION)/$(TYPOS_ARCHIVE)"
	@echo "$(TYPOS_SHA256)  $(TMP)/$(TYPOS_ARCHIVE)" | shasum -a 256 -c -
	# Extract the whole archive: the binary is stored as ./typos, which GNU tar
	# does not match by the bare name "typos" while bsdtar does.
	tar -xzf $(TMP)/$(TYPOS_ARCHIVE) -C $(TMP)/typos-$(TYPOS_VERSION)
	@test -x $(TYPOS) || { echo "typos binary missing after extraction" >&2; exit 1; }
	@rm -f $(TMP)/$(TYPOS_ARCHIVE)

$(VALE):
	@test -n "$(VALE_SHA256)" || { echo "Unsupported Vale platform: $(UNAME_S)/$(UNAME_M)"; exit 1; }
	@mkdir -p $(TMP)/vale-$(VALE_VERSION)
	curl --fail-with-body --location --silent --show-error --retry 3 \
	  --output $(TMP)/$(VALE_ARCHIVE) \
	  "https://github.com/vale-cli/vale/releases/download/v$(VALE_VERSION)/$(VALE_ARCHIVE)"
	@echo "$(VALE_SHA256)  $(TMP)/$(VALE_ARCHIVE)" | shasum -a 256 -c -
	tar -xzf $(TMP)/$(VALE_ARCHIVE) -C $(TMP)/vale-$(VALE_VERSION)
	@test -x $(VALE) || { echo "Vale binary missing after extraction" >&2; exit 1; }
	@rm -f $(TMP)/$(VALE_ARCHIVE)

clean: ## Remove downloaded tools and caches
	rm -rf $(TMP) node_modules scripts/__pycache__

vendored: ## Verify vendored third-party files match their recorded checksums
	@python3 scripts/check_vendored.py
