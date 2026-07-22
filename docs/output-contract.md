# Markdown output contract

`grab2md` converts the fetched or local HTML document to Markdown. Existing
content behavior remains the default; metadata front matter is opt-in with
`--metadata` on direct conversion, `batch`, and `crawl`.

## URLs

For HTTP(S) documents, relative Markdown links and image references are resolved
against the final response URL. A valid HTML `<base href>` overrides that base
for document references. Root-relative, path-relative, protocol-relative,
query, and fragment components follow standard URL joining rules. Fragment-only
links and non-web schemes such as `mailto:` remain unchanged.

This canonicalization occurs before image downloading and archive link
rewriting. Downloaded image references can therefore be replaced by local image
paths, and successful crawl/batch targets can still be rewritten relative to
the containing Markdown file.

Crawl frontier identity excludes URL fragments because fragments identify a
location within an already-fetched representation. Query strings remain part
of identity because servers may return different resources for different
queries.

Local HTML references are not canonicalized. They remain source-relative so
local links retain their meaning and the guarded local-image copier can resolve
them beneath the source document directory.

## Character decoding

Static HTTP HTML in single-page, batch, and crawl paths is decoded through the
same deterministic boundary. A valid HTTP `charset`
declaration is authoritative, followed by a Unicode byte-order mark and an
HTML `<meta charset>` or `content` declaration found near the start of the
document. Undeclared content is decoded as UTF-8 when valid and otherwise uses
the HTML-compatible Windows-1252 fallback. Unknown declared encodings and
content that is invalid for its explicit encoding fail acquisition instead of
silently returning corrupted text. Local HTML input remains explicitly UTF-8.

## Metadata

With `--metadata`, output starts with YAML-compatible front matter. Populated
fields appear in this fixed order:

```yaml
---
title: "Page title"
author: "Author name"
date: "2026-07-16T10:30:00Z"
canonical_url: "https://example.com/article"
description: "Page description"
language: "en-US"
---
```

All values are JSON-quoted strings, which are also valid YAML scalars. Missing
fields are omitted. Extraction uses standard HTML title, meta, canonical-link,
and language attributes. Open Graph/Twitter title and description fields and
article publication fields are recognized. For a remote document without an
explicit canonical link, `canonical_url` is the final response URL. Local files
do not receive a fabricated canonical URL. Invalid, credential-bearing, and
non-HTTP(S) canonical links are treated as absent, so they cannot make archive
registration fail after an output has been written.

Page-authored canonical links are descriptive metadata, not archival identity.
They do not suppress conversion or persistence of another requested or final
URL, because an inaccurate or hostile declaration is not proof that two pages
contain equivalent content. Redirect final URLs remain acquisition identities
and are deduplicated.

The contract deliberately does not infer missing authors or dates from page
text and does not execute JSON-LD. This keeps output deterministic and avoids
turning ambiguous heuristics into asserted metadata.
