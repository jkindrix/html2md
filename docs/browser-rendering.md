# Optional JavaScript rendering

The default conversion path uses `requests` and does not execute page code.
`grab2md URL --render-js` is an explicit, URL-only mode for pages whose
meaningful DOM is created by JavaScript.

## Installation

Browser automation is isolated from the base package:

```bash
python -m pip install "grab2md[render]"
python -m playwright install chromium
grab2md https://example.com/app --render-js --output app.md
```

For a page requiring an existing browser session, create Playwright storage
state in a separate login process, restrict it to the current user, and pass it
explicitly:

```bash
chmod 600 session-state.json
grab2md https://example.com/app --render-js \
  --storage-state session-state.json
```

Playwright versions require matching browser binaries. Re-run the browser
installation after upgrading the render extra. The browser cache requires a few
hundred megabytes; the base/static installation downloads none of it.

## Resource and security boundary

Rendered pages execute untrusted JavaScript in a fresh, headless Chromium
context. By default the context is non-persistent; `--storage-state` can seed it
from an owner-only Playwright state file created by a separate login process.
The context:

- never modifies the supplied storage-state file and does not persist resulting
  cookies or local storage;
- blocks service workers, downloads, images, media, and fonts;
- resolves the requested hostname once, validates every returned address, and
  pins Chromium to one validated numeric address while retaining the URL
  hostname for HTTP and TLS identity;
- permits subresources only from the explicitly requested origin and blocks all
  cross-origin requests and top-level redirects;
- fails all other Chromium DNS lookups and bypasses system proxy resolution;
- rejects credential-bearing and non-HTTP(S) network URLs;
- caps navigation at 30 seconds, post-load settling at 500 milliseconds,
  aggregate decoded browser response data at 50 MiB, requests at 250, and
  serialized HTML at 10 MiB; and
- closes the browser after one conversion.

Private, loopback, link-local, and metadata source destinations are rejected by
default. `--allow-private-network` explicitly permits a trusted internal or
local source while retaining hostname pinning and the remaining controls.
`--insecure` also disables certificate verification inside Chromium and carries
the same interception risk as the static path. Browser/JSON cookie import is
rejected in render mode rather than silently creating an authenticated browser.
Downloaded images are fetched after rendering through the existing guarded
image policy, not by Chromium.

These controls reduce exposure but do not make hostile JavaScript harmless.
Chromium is a large native-code dependency and must be kept patched. Run render
mode with ordinary user privileges and avoid sensitive network environments.

## Scope

Rendering is supported by direct URL conversion only. Batch and crawl remain
static so their single-fetch, robots, rate-limit, retry, and checkpoint
contracts are not bypassed by a second browser request. Expanding rendering to
those workflows requires a browser-backed fetch result integrated at the
crawler boundary, not an after-the-fact second fetch.

Cross-origin redirects and API-driven applications may render incompletely
because their requests are blocked. This is an intentional default-deny
trade-off; `--allow-private-network` changes address classification only and is
not an unrestricted cross-origin switch.
