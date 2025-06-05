# Image Download Feature Demo

The html2md tool now supports downloading images from web pages and storing them locally. This feature helps create self-contained markdown documentation with all assets included.

## How to Use

### Basic Usage

```bash
# Convert a URL and download all images
html2md convert https://example.com --output output.md --download-images

# Specify a custom directory for images
html2md convert https://example.com --output output.md --download-images --images-dir assets

# Convert local HTML file with image downloading
html2md convert file.html --output output.md --download-images --local
```

### Batch Processing with Images

```bash
# Process multiple URLs from markdown files and download images
html2md batch input.md --output-dir output --download-images
```

### Recursive Crawling with Images

```bash
# Crawl a website and download all images
html2md crawl https://example.com --output-dir docs --download-images
```

## Features

1. **Automatic Image Detection**: Extracts images from:
   - `<img>` tags (src attribute)
   - `<img>` tags with srcset for responsive images
   - CSS background-image properties

2. **Smart File Naming**: 
   - Generates safe filenames from URLs
   - Handles naming conflicts automatically
   - Preserves file extensions when possible

3. **Local Storage**:
   - Images are saved in a subdirectory (default: "images")
   - Maintains relative paths for portability
   - Organizes images by domain when crawling

4. **URL Rewriting**:
   - Automatically updates markdown links to point to local images
   - Preserves alt text and other attributes
   - Works with both absolute and relative URLs

## Example Output Structure

```
output/
├── example.com.md
└── images/
    ├── logo.png
    ├── banner.jpg
    └── icon.svg
```

## Error Handling

- Failed downloads are logged but don't stop the conversion
- Original URLs are preserved if download fails
- Network errors are handled gracefully

## Configuration

The feature respects existing session management and cookie settings, allowing authenticated image downloads when needed.