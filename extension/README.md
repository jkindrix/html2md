# HTML2MD Chrome Extension

A browser extension for quickly converting web content to Markdown.

## Stabilization status

The supported alpha surface is intentionally limited to converting the active tab as a full page, selection, or main article, with popup preview, clipboard copy, or download output. Direct URL capture, batch URL conversion, and element-selection modes and handlers have been removed.

## Features

- **One-Click Conversion**: Convert any web page to Markdown with a single click
- **Multiple Conversion Modes**: Convert entire pages, selections, or just the main article content
- **Customizable Output**: Control how your Markdown is formatted with advanced settings
- **Explicit Content Scope**: Full-page mode keeps authored page content,
  selection mode converts exactly the selected range, and article mode uses
  packaged Mozilla Readability heuristics
- **Multiple Output Options**: View directly in the extension, copy to clipboard, or download as a file
- **Dark Mode Support**: Beautiful light and dark themes for the extension UI

## Installation

### From Chrome Web Store

1. Visit the Chrome Web Store (link will be provided when published)
2. Click "Add to Chrome"
3. Confirm the installation

### Manual Installation (Developer Mode)

1. Download or clone this repository
2. Open Chrome and go to `chrome://extensions/`
3. Enable "Developer mode" in the top-right corner
4. Click "Load unpacked" and select the extension directory
5. The HTML2MD extension is now installed

## Usage

### Basic Usage

1. Navigate to any web page you want to convert
2. Click the HTML2MD extension icon in your browser toolbar
3. Select your conversion options (Full Page, Selection Only, or Main Article)
4. Click "Convert to Markdown"
5. The result will be shown, copied, or downloaded based on your settings

## Advanced Settings

### Markdown Formatting Options

- **Heading Style**: Choose between ATX (`# Heading`) or Setext (`Heading\n=====`) style headings
- **Link Style**: Choose between inline (`[text](url)`) or reference (`[text][id]`) style links
- **List Marker**: Select your preferred list marker (-, *, or +)

### Content Processing Options

- **Include Images**: Toggle whether images should be included in the Markdown output
- **Format Tables**: Enable special handling for HTML tables
- **Format Code Blocks**: Enable fenced code blocks for code sections
- **Keep Links Inline**: Control how links are formatted

## Permissions

The extension requests no persistent host access and exposes no resources to arbitrary pages.

| Permission | Purpose |
|---|---|
| `activeTab` | Limit conversion access to the tab on which the user invoked the popup |
| `scripting` | Extract the selected active-tab content |
| `storage` | Persist local formatting preferences |
| `downloads` | Save generated Markdown when requested |
| `clipboardWrite` | Copy generated Markdown when requested |

## Development

### Project Structure

```
html2md-extension/
├── manifest.json       # Extension manifest
├── popup.html          # Main extension popup
├── popup.js            # Popup functionality
├── styles.css          # Styles for the popup
├── logger.js           # Production-safe diagnostic boundary
├── readability.js      # Vendored Mozilla Readability 0.6.0
├── turndown.js         # HTML to Markdown conversion library
├── THIRD_PARTY_NOTICES.md # Upstream copyright, license, and provenance
└── images/             # Extension icons and images
```

### Building from Source

1. Clone the repository
2. Make your changes
3. Test locally using Chrome's "Load unpacked" feature
4. Package for distribution

Run the committed static regression and syntax checks with:

```bash
for file in extension/*.js extension/tests/*.js; do node --check "$file"; done
node --test extension/tests/*.test.js
node extension/tests/chromium-smoke.js
```

The Chromium smoke test loads the directory as an unpacked extension under Xvfb and verifies popup controls/settings, full-page/article/selection extraction, HTML conversion, user-content preservation, preview, clipboard, download, the declared permission set, and denial without an active-tab host grant.

## License

Copyright (c) 2025-2026 Justin Kindrix. Distributed under the [MIT License](../LICENSE).

## Credits

- Built by Justin Kindrix
- Uses [Turndown](https://github.com/mixmark-io/turndown) for HTML to Markdown conversion
- Uses [Mozilla Readability](https://github.com/mozilla/readability) 0.6.0 for explicit article extraction
- Retains Turndown v7.1.1 copyright, MIT terms, provenance, and modification notes in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)
- Inspired by the [HTML2MD](https://github.com/jkindrix/html2md) command-line tool
