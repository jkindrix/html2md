# HTML2MD Encoding Flow Analysis

## Summary

The html2md codebase has a potential Unicode handling issue where HTML entities in configuration footer markers may not match the converted markdown content, causing the trimmer to fail to find footer boundaries.

## Encoding Flow

### 1. HTML Fetching and Decoding (converter.py)

- **Lines 75-92**: When fetching HTML via `requests.get()`:
  - The requests library detects encoding from the HTTP response headers
  - If no encoding is detected, it defaults to UTF-8 (line 83)
  - `response.text` returns the decoded Unicode string
  - The library automatically handles decompression (gzip/brotli)

- **Lines 211-212**: For local files:
  - Files are read with UTF-8 encoding explicitly

### 2. HTML to Markdown Conversion

- **Line 167**: `markdownify` converts HTML to Markdown
  - **Critical behavior**: markdownify converts ALL HTML entities to their Unicode equivalents
  - `&copy;` → `©`
  - `&#169;` → `©`
  - `&#xA9;` → `©`
  - This is standard behavior for HTML parsers

### 3. Footer Marker Configuration (config.json)

- Footer markers are stored as plain strings in JSON
- No HTML entity decoding is performed when loading the config
- Examples from config:
  - Line 55: `"Content and code samples on this page are subject to the licenses described in the"`
  - These are stored exactly as written

### 4. String Matching in Trimmer (trimmer.py)

- **Lines 42, 50, 83**: Uses Python's `str.find()` method for exact string matching
- No HTML entity decoding is performed on the footer markers
- If config has `"&copy; 2024"` but markdown has `"© 2024"`, the match will fail

## The Problem

1. User adds footer marker to config: `"footer_marker": "&copy; 2024 Company"`
2. HTML contains: `<p>&copy; 2024 Company</p>`
3. Markdownify converts to: `"© 2024 Company"`
4. Trimmer searches for: `"&copy; 2024 Company"` (exact string from config)
5. **Result**: No match found, footer trimming fails

## Evidence

Test results show:
- `'&copy;' == '©'` returns `False`
- `'&copy;'.encode('utf-8')` = `b'&copy;'` (6 bytes)
- `'©'.encode('utf-8')` = `b'\xc2\xa9'` (2 bytes)

## Solutions

### Option 1: Pre-process Config Markers (Recommended)
Add HTML entity decoding when loading footer markers from config:

```python
import html
# In trimmer.py, when reading footer_marker:
footer_marker = html.unescape(rule["footer_marker"])
```

### Option 2: Use Unicode in Config
Document that users must use Unicode characters, not HTML entities:
- ❌ Wrong: `"footer_marker": "&copy; 2024"`
- ✅ Right: `"footer_marker": "© 2024"`

### Option 3: Normalize Both Sides
Convert both the markdown content and footer markers to a canonical form before matching.

### Option 4: Smart Matching
Implement a smarter matching function that tries both the original and HTML-decoded versions of the footer marker.

## Impact

This issue affects any domain configuration that uses HTML entities in footer markers, particularly:
- Copyright symbols (`&copy;`)
- Trademark symbols (`&trade;`, `&reg;`)
- Special quotes (`&ldquo;`, `&rdquo;`)
- Non-breaking spaces (`&nbsp;`)
- Any other HTML entities

## Recommendation

Implement Option 1 (pre-process config markers) as it:
- Maintains backward compatibility
- Allows users to use either format in config
- Follows the principle of least surprise
- Minimal code change required