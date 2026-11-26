# Security Policy

## Architectural Trust Boundaries

Ad Library Insights processes public third-party HTML and ad copy from the Meta Ad Library and runs locally on `127.0.0.1`:

- **Prompt-Injection Delimiting:** Competitor text excerpts, headlines, and video frame descriptions written to specialist data packs (`copy.md`, `creative.md`, `brief.md`) are sanitized and wrapped inside `<untrusted_ad_content>` tags with spoofed closing tags neutralized.
- **Sandboxed Sub-Process Execution:** When invoked from Studio's in-page runner, `ai_runner.py` spawns `claude -p` with restricted read-only file tools (`Read,Glob,Grep`), `--strict-mcp-config`, `--disallowedTools mcp__*`, and cwd confined to the analysis pack folder.
- **Localhost-Only Binding:** The Studio web server binds exclusively to `127.0.0.1`.
- **Ephemeral Video Cleanup:** On-demand video inspection (`inspect_video`) enforces a strict size ceiling (`50 MB`) and cleans temporary `.mp4` downloads after extracting timestamped contact sheets.

## Reporting a Vulnerability

If you discover a security issue (such as a sandbox escape, `<untrusted_ad_content>` delimiter bypass, SSRF, or unsafe HTML rendering in Studio/MCP App), please report it privately via **GitHub Security Advisories** (`Security` -> `Report a vulnerability` on [KlausZanaj/ad_library_insights](https://github.com/KlausZanaj/ad_library_insights/security/advisories/new)) rather than opening a public issue.
