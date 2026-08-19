# Release Process

## Overview

Shannon releases are triggered by git tags. The CI workflow builds Docker images for all services, builds desktop apps for macOS/Windows/Linux, pushes images to Docker Hub, and creates a GitHub Release with desktop binaries attached.

## Cutting a Release

1. Update `CHANGELOG.md` with the release notes
2. Ensure version strings are updated where needed (see checklist below)
3. Tag the release:
   ```bash
   git tag v0.4.0
   git push origin v0.4.0
   ```
4. CI automatically:
   - Builds Docker images for agent-core, orchestrator, llm-service, gateway, playwright-service
   - Pushes to Docker Hub as `waylandzhang/<service>:v0.4.0` and `:latest`
   - Builds desktop apps (macOS universal, Windows MSI/NSIS, Linux AppImage/deb)
   - Creates a GitHub Release with desktop binaries and `latest.json` for Tauri auto-update

## Docker Hub Images

All images are published under the `waylandzhang` Docker Hub org:

```
waylandzhang/agent-core:<version>
waylandzhang/orchestrator:<version>
waylandzhang/llm-service:<version>
waylandzhang/gateway:<version>
waylandzhang/playwright-service:<version>
```

Tags: `v0.4.0` (pinned) and `latest` (rolling).

## User Installation

End users install via the one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/Kocoro-lab/Shannon/v0.4.0/scripts/install.sh | bash
```

Or with a specific version:

```bash
curl -fsSL https://raw.githubusercontent.com/Kocoro-lab/Shannon/main/scripts/install.sh | SHANNON_VERSION=v0.4.0 bash
```

This downloads `docker-compose.release.yml`, config files, migrations, the WASM interpreter, and starts all services.

## Manual Trigger

The release workflow can also be triggered manually from GitHub Actions:

1. Go to Actions > "Release - Build and Push Docker Images"
2. Click "Run workflow"
3. Enter the version tag (e.g., `v0.4.0`)

## Version Bump Checklist

Before tagging a new release:

- [ ] `CHANGELOG.md` updated with notable changes
- [ ] `scripts/install.sh` default version updated (`SHANNON_VERSION`)
- [ ] `desktop/src-tauri/tauri.conf.json` version field (desktop app version)
- [ ] `desktop/package.json` version field
- [ ] Any hardcoded version references in docs
- [ ] Run `make ci` to verify tests pass
- [ ] Verify `docker-compose.release.yml` matches current `docker-compose.yml` structure (env vars, volumes, healthchecks)

## Hotfix Process

For urgent fixes on a released version:

1. Create a branch from the release tag: `git checkout -b hotfix/v0.4.1 v0.4.0`
2. Apply the fix
3. Tag: `git tag v0.4.1`
4. Push both: `git push origin hotfix/v0.4.1 v0.4.1`
5. Merge the hotfix branch back to `main`
