# Third-Party Notices

This extension contains the following third-party code.

## Mozilla Readability 0.6.0

- Project: Mozilla Readability
- Version: 0.6.0
- Published package: `@mozilla/readability@0.6.0`
- Upstream source: https://github.com/mozilla/readability
- Vendored file: `readability.js` (unmodified `Readability.js`)
- SHA-256: `34dcab3d0832d0019f02990eed6b6124e029e8c32b9f0c6f2550544ff8dff174`
- License: Apache License 2.0, reproduced in `READABILITY_LICENSE.md`

## Turndown v7.1.1

- Project: Turndown
- Version used as the derivation baseline: 7.1.1
- Upstream source: https://github.com/mixmark-io/turndown/tree/v7.1.1
- Vendored derivative: `turndown.js`
- Local modifications: HTML2MD-specific inert parsing, formatting, escaping,
  and conversion rules
- Integrity model: maintained and regression-tested as a local derivative; it
  is not represented as an unmodified, upstream-hash-pinned asset

MIT License

Copyright (c) 2017 Dom Christie

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Vendored-asset review

As reviewed on 2026-07-17, Mozilla Readability and the Turndown derivative are
the only third-party source assets declared or identified in the extension
tree. The remaining JavaScript, HTML, CSS, and image assets are project-authored
assets. If another third-party asset is added, its copyright, version, source,
modifications, and required license text must be added here before distribution.
