# Vendored frontend libraries

Served by Home Assistant next to `edata-card.js` (browser-cached for a month),
so the card loads without reaching external CDNs. Keep the version in the file
name: a new version gets a new URL and is never served stale from the cache.

| File | Source | License |
| --- | --- | --- |
| `lit-core-3.2.1.min.js` | https://cdn.jsdelivr.net/gh/lit/dist@3.2.1/core/lit-core.min.js | BSD-3-Clause (Google LLC) |
