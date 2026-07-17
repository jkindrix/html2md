# ADR 0002: Select conservative main-content extraction

- Status: Accepted
- Date: 2026-07-17
- Decision owners: Project maintainers
- Scope: explicit main-content extraction in the Python converter

## Context

Full-document conversion must remain lossless and the default. The former
`--trim` path instead truncated generated Markdown using domain names, heading
positions, and footer words. It could delete legitimate sections such as
References and License, and its packaged site rules aged independently of the
converter.

Main-content extraction is still useful when explicitly requested. The relevant
Python choices were measured rather than selected from popularity claims:

- `readability-lxml` 0.8.4.1 emits ordinary HTML and supports Python 3.8–3.13.
  A clean environment installed four transitive packages: `chardet`,
  `cssselect`, `lxml`, and `lxml-html-clean`. The last package must be declared
  explicitly because the release's `lxml[html_clean]` declaration does not
  install it with current lxml.
- Trafilatura 2.1.0 is actively maintained and exposes precision/recall controls,
  links, images, tables, and multiple output formats. A clean environment
  installed fourteen transitive packages. Its HTML output uses an extraction
  dialect (`head`, `ref`, `graphic`, `row`, and `cell`) rather than ordinary
  source HTML, while its Markdown output would bypass html2md's single Markdown
  conversion pipeline.
- A semantic-only implementation preserves markup well but cannot handle the
  common generic `div` article case.

The reproducible corpus in `tests/fixtures/extraction` covers a semantic
article, documentation with code/table/License content, a generic-div article,
and an ambiguous card index. `benchmarks/main_content/benchmark.py` measures
required-content recall, boilerplate rejection, and honest failure. With
Beautiful Soup 4.13.4, Markdownify 1.1.0, readability-lxml 0.8.4.1,
lxml-html-clean 0.4.5, and Trafilatura 2.1.0, the two conservative hybrid
candidates produced the same result:

| Fixture | Required recall | Boilerplate rejection | Disposition |
|---|---:|---:|---|
| Semantic article | 100% | 100% | content |
| Documentation | 100% | 100% | content |
| Generic-div article | 100% | 100% | content |
| Ambiguous card index | n/a | 100% | explicit failure |

Raw conversion retained all boilerplate. Standalone readability retained
article/documentation furniture and lost measured article structure. Standalone
Trafilatura handled the three content fixtures but returned a fabricated main
result for the ambiguous index. The complete matrix can be reproduced with:

```bash
python -m venv /tmp/html2md-extractors
/tmp/html2md-extractors/bin/pip install \
  beautifulsoup4==4.13.4 markdownify==1.1.0 \
  readability-lxml==0.8.4.1 lxml-html-clean==0.4.5 trafilatura==2.1.0
/tmp/html2md-extractors/bin/python benchmarks/main_content/benchmark.py
```

## Decision

Use a conservative semantic-plus-readability strategy for explicit `main`
mode:

1. Select one substantial `<article>` when exactly one exists.
2. Otherwise select one `<main>` when exactly one exists.
3. Otherwise run readability-lxml and accept its ordinary-HTML result only when
   it meets a minimum text-and-paragraph confidence boundary.
4. If no candidate meets that boundary, fail clearly and direct the caller to
   full mode or an explicit selector. Never silently fall back to the full page.
5. Feed the selected HTML into the existing document preparation and
   Markdownify pipeline. Extraction chooses HTML; it does not own Markdown
   serialization.

The direct dependencies will be `readability-lxml` and `lxml-html-clean` with
compatible version bounds. This chooses the smaller standard-HTML integration
because the measured hybrid output tied the larger Trafilatura hybrid.

## Consequences

Main mode is heuristic and can fail on unusual pages, but failure is explicit
and recoverable. Semantic pages retain their original link, image, table, code,
and section markup. Generic article pages gain a maintained extraction
algorithm without introducing a second Markdown renderer. Full mode remains
unaffected.

The committed benchmark is a selection record, not a claim of universal
extractor quality. New extractor versions or strategies must beat or match the
corpus, add a fixture for the motivating failure, preserve the honest-failure
boundary, and pass dependency/security review before replacing this decision.

## Primary references

- [Trafilatura Python usage and extraction controls](https://trafilatura.readthedocs.io/en/latest/usage-python.html)
- [Trafilatura 2.1.0 package metadata](https://pypi.org/project/trafilatura/)
- [readability-lxml 0.8.4.1 package metadata](https://pypi.org/project/readability-lxml/)
- [Mozilla Readability API and heuristic boundaries](https://github.com/mozilla/readability)
