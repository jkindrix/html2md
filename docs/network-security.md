# Outbound network security

Remote documents and links are untrusted input. Every production HTTP(S)
request initiated directly by grab2md must use the shared guarded transport in
`grab2md.network.safe_http`. A bare `requests.get`, `Session.request`, urllib
fetch, or independently resolving proxy is not an accepted acquisition path.

## Default policy

The static converter, batch processor, crawler, robots parser, and image
downloader:

- accept only HTTP(S) URLs without embedded credentials;
- resolve an origin once and reject the entire result if any address is not
  globally routable;
- connect to a validated numeric address while retaining the original Host,
  TLS SNI, and certificate hostname;
- cache an origin's validated addresses for the lifetime of a multi-request
  operation, preventing later same-host DNS rebinding;
- disable environment and configured proxies because proxy-side resolution
  would reopen the validation/connection race;
- follow redirects manually, validate and pin every new origin before sending
  the next request, and strip explicit Cookie and cross-origin Authorization
  headers;
- reject HTTPS-to-HTTP redirect downgrades;
- apply IPv4 destination classification to IPv4-mapped, 6to4, deprecated
  IPv4-compatible `::/96`, and well-known `64:ff9b::/96` NAT64 addresses; and
- cap static page and crawl bodies at 10 MiB and robots files at 1 MiB.

The supported Requests version is checked at runtime for the adapter hooks
required by numeric-address pinning. An incompatible transport fails closed
instead of silently falling back to ordinary hostname resolution. Arbitrary
network-specific NAT64 prefixes cannot be identified from an IPv6 destination
alone and remain an operator/network boundary.

Image downloads use the same connection primitive plus their stricter media,
aggregate-size, and output-path rules.

## Private-network opt-in

`--allow-private-network` is required for intentional intranet, loopback, or
local-development destinations. It changes only address classification. URL
validation, DNS pinning, redirect handling, proxy bypass, response limits, and
TLS certificate verification remain enabled.

`--insecure` is separate: it disables TLS certificate verification but does not
authorize private addresses. Use either option only for a destination under the
operator's control.

## Browser rendering

Chromium is launched with a resolver rule that maps only the requested hostname
to its prevalidated numeric address and makes every other DNS lookup fail. The
route policy permits only that source origin, so cross-origin subresources and
top-level redirects are blocked. `--allow-private-network` may authorize a
trusted private source but does not relax the same-origin boundary.

This optional path does not use the Requests transport's socket-level adapter.
Its pinning boundary depends on the supported Chromium runtime honoring
`--host-resolver-rules`; grab2md also launches with `--no-proxy-server`, blocks
service workers, and intercepts every browser request through the origin route
policy. The adversarial Chromium gate verifies that runtime contract. These two
pinning mechanisms are intentionally documented separately rather than treated
as identical enforcement.

## Maintainer rule

New code that retrieves an untrusted or remotely controlled URL must reuse
`DestinationPolicy`, `PinnedHttpClient`, or `guarded_request`, and must include
tests for private-address rejection, redirect revalidation, and byte limits as
applicable. A new browser-backed path must also prove that the browser connects
to the validated address rather than resolving independently.

Crawler link scope is applied before robots lookups, and each redirected crawl
destination is checked against both the established final-origin scope and its
robots policy before the redirected page request is sent.
