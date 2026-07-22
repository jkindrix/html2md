# grab2md configuration examples

The configuration CLI validates values against the same schema used when the
application loads them. Prefer it to editing JSON by hand:

```bash
grab2md config path
grab2md config show
grab2md config show-options
grab2md config list-cli-defaults
```

## Direct-conversion defaults

The persisted namespace is named `convert` because it also backs the hidden
compatibility alias. The primary invocation remains `grab2md SOURCE...`.

```bash
grab2md config set-cli-default convert content_mode main
grab2md config set-cli-default convert metadata true
grab2md https://example.com
```

Reset one option without changing the others:

```bash
grab2md config set-cli-default convert content_mode --reset
```

## Batch and crawl defaults

```bash
grab2md config set-cli-default batch hierarchical true
grab2md config set-cli-default crawl max_pages 200
grab2md config set-cli-default crawl rate_limit 30
grab2md batch input.md --output-dir output
grab2md crawl https://docs.example.com --output-dir documentation
```

Values are typed: booleans use `true` or `false`, optional values accept `null`,
and invalid enum values or crawl budgets are rejected before the file is
replaced.

## Cookie defaults

Do not make browser-cookie extraction a global default unless every direct
conversion should receive those credentials. The portable path is an explicit,
owner-private exported cookie file for one invocation:

```bash
chmod 600 cookies.json
grab2md https://example.com --cookie-json cookies.json
```

Automatic Chrome extraction is generally unavailable for current app-bound
cookie stores and fails closed. See the main README for the bounded Firefox and
legacy Windows Chrome behavior.

## Configuration file locations

The default path is platform-specific:

- Linux: `$XDG_CONFIG_HOME/grab2md/config.json`, falling back to
  `~/.config/grab2md/config.json`
- macOS: `~/Library/Application Support/grab2md/config.json`
- Windows: `%APPDATA%\grab2md\config.json`

`GRAB2MD_CONFIG_PATH` overrides the complete file path. `grab2md config path`
prints the effective location.

The loader merges a partial file with current defaults, so examples need not
copy the entire schema:

```json
{
  "logging": {"level": "WARNING"},
  "cli_defaults": {
    "convert": {"content_mode": "main", "metadata": true},
    "batch": {"hierarchical": true},
    "crawl": {"max_pages": 200, "rate_limit": 30}
  }
}
```

Direct edits do not receive the CLI writer's validation, backup, locking, and
atomic replacement until grab2md next loads or rewrites the file. Use
configuration commands for routine changes.

## Reset all settings

```bash
grab2md config reset
```
