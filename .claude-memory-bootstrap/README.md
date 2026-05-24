# Memory bootstrap (for WSL migration)

These memory files were captured from the VMware-Linux dev environment on
2026-05-24 so they can survive the migration to WSL2 (where Claude Code's
project-keyed memory path changes and otherwise starts empty).

**This folder is transient.** After your first successful Claude session in
WSL, the bootstrap script copies these into the right per-project memory
location at `~/.claude/projects/<auto-detected-slug>/memory/`, and you
should `git rm -rf .claude-memory-bootstrap/` to keep them out of the repo
long-term. They contain personal collaboration preferences that don't
belong in shared source control.

See `docs/MIGRATION_TO_WSL.md` and `scripts/wsl_first_run.sh` for the full flow.
