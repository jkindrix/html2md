# HTML2MD Chrome Extension

A browser extension for quickly converting web content to Markdown.

## Features

- **One-Click Conversion**: Convert any web page to Markdown with a single click
- **Multiple Conversion Modes**: Convert entire pages, selections, or just the main article content
- **Customizable Output**: Control how your Markdown is formatted with advanced settings
- **Smart Content Trimming**: Automatically removes navigation, sidebars, and other non-content elements
- **Multiple Output Options**: View directly in the extension, copy to clipboard, or download as a file
- **Keyboard Shortcuts**: Quick access with customizable keyboard shortcuts
- **Context Menu Integration**: Right-click to convert content
- **Dark Mode Support**: Beautiful light and dark themes for the extension UI
- **CLI Integration**: Optional integration with the HTML2MD command-line tool

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

### Keyboard Shortcuts

- **Ctrl+Shift+M** (macOS: **Command+Shift+M**): Open the HTML2MD popup
- **Alt+M**: Convert the current selection to Markdown and copy to clipboard

### Context Menu

Right-click anywhere on a page to access the following options:

- **Convert page to Markdown**: Convert the entire page and download as a file
- **Convert selection to Markdown**: Convert only the selected content and copy to clipboard
- **Open HTML2MD settings**: Open the settings panel

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

### CLI Integration

If you have the HTML2MD command-line tool installed, you can provide its path in the settings to enable enhanced conversion features.

## Integration with HTML2MD CLI

For advanced users, this extension can integrate with the HTML2MD command-line tool to provide enhanced conversion capabilities. To enable this integration:

1. Install the HTML2MD CLI tool from [GitHub](https://github.com/jkindrix/html2md)
2. Open the extension settings
3. Enter the path to the HTML2MD executable in the "CLI Tool Path" field
4. Save your settings

## Development

### Project Structure

```
html2md-extension/
├── manifest.json       # Extension manifest
├── popup.html          # Main extension popup
├── popup.js            # Popup functionality
├── styles.css          # Styles for the popup
├── background.js       # Background script
├── turndown.js         # HTML to Markdown conversion library
└── images/             # Extension icons and images
```

### Building from Source

1. Clone the repository
2. Make your changes
3. Test locally using Chrome's "Load unpacked" feature
4. Package for distribution

## License

MIT License - see the LICENSE file for details.

## Credits

- Built by Justin Kindrix
- Uses [Turndown](https://github.com/mixmark-io/turndown) for HTML to Markdown conversion
- Inspired by the [HTML2MD](https://github.com/jkindrix/html2md) command-line tool
