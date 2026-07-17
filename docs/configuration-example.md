# HTML2MD Configuration Examples

## Setting CLI Defaults

You can now configure default values for CLI options so you don't have to specify them every time.

### Example 1: Always use browser cookies by default

```bash
# Set browser_cookies as default for convert command
html2md config set-cli-default convert browser_cookies true

# Now this command will automatically use browser cookies
html2md convert https://example.com
```

### Example 2: Use hierarchical folders by default for batch operations

```bash
# Set hierarchical as default for batch command
html2md config set-cli-default batch hierarchical true

# Now batch operations will create hierarchical domain folders
html2md batch input.md -o output
# Creates: output/com/example/www/
```

### Example 3: Configure multiple defaults

```bash
# Set multiple defaults
html2md config set-cli-default convert browser_cookies true
html2md config set-cli-default convert browser chrome
html2md config set-cli-default batch hierarchical true
html2md config set-cli-default crawl max_pages 200
html2md config set-cli-default crawl hierarchical true
```

### View current defaults

```bash
# List all CLI defaults
html2md config list-cli-defaults
```

### Using the config file directly

You can also edit the config file directly. The config file location is:
- Linux: `~/.config/html2md/config.json`
- macOS: `~/Library/Application Support/html2md/config.json`
- Windows: `%APPDATA%\html2md\config.json`

Example config file with CLI defaults:
```json
{
  "domains": {},
  "logging": {"level": "WARNING"},
  "browser": {"preferred": "chrome"},
  "cli_defaults": {
    "batch": {
      "hierarchical": true,
      "flatten": false,
      "flatten_all": false,
      "content_mode": "full",
      "selector": null,
      "visualize": false,
      "quiet": false
    },
    "crawl": {
      "hierarchical": true,
      "flatten": false,
      "follow": "domain-only",
      "max_depth": 3,
      "max_pages": 200,
      "content_mode": "full",
      "selector": null,
      "visualize": false,
      "quiet": false
    },
    "convert": {
      "browser_cookies": true,
      "no_cookies": false,
      "browser": "chrome",
      "content_mode": "full",
      "selector": null,
      "download_images": false,
      "images_dir": "images",
      "fancy": false,
      "local": false
    }
  }
}
```

### Show config file path

```bash
html2md config path
```

### Reset to defaults

```bash
html2md config reset
```
