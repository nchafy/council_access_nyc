# axe-core, vendored

`axe.min.js` is a third-party file committed verbatim. This records what it is, where
it came from, and how to verify or replace it.

| | |
|---|---|
| Package | `axe-core` |
| Version | **4.13.0** |
| License | MPL-2.0 (`LICENSE`, plus `LICENSE-3RD-PARTY.txt`) |
| Source | `https://registry.npmjs.org/axe-core/-/axe-core-4.13.0.tgz` |
| Tarball integrity | `sha512-UzGt8zg7Ny8djbYMhxl2zuEevVa7r2gJjYY5Lwr1xM7+XU2nd6CkIWFTVcCIbAP63vSz71NaVyyuSk9lHKcy0A==` (as published by the registry) |
| `axe.min.js` sha256 | `c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1` |
| Vendored | 2026-09-23 |

`tests/unit/test_vendor.py` asserts the sha256 and the version string on every run, so
the file cannot change without a reviewable diff to that test.

## Why it is committed rather than installed

R39 requires axe over every pre-rendered page **in CI**. The alternative to committing
it is `npm ci` in the CI job, which trades one committed 567 KB file for a package
manager, a lockfile, a Node toolchain and a registry fetch inside the job that renders
untrusted upstream content. `docs/phase-1-scope.md` §4.5 wants the build to pull nothing
and hold no secrets; one checksummed file honours that, and a registry hop does not.

It is a **development** artifact. It is never copied into `site/`, never referenced by a
page we publish, and never loaded by a browser outside a test run — `scripts/axe_check.py`
injects it through the DevTools protocol, which is why no `script-src` change is needed
to run it against the real CSP.

## Updating it

```bash
V=4.13.1                               # the version you intend to pin
curl -sSfL -o /tmp/axe.tgz "https://registry.npmjs.org/axe-core/-/axe-core-$V.tgz"
curl -s https://registry.npmjs.org/axe-core | \
  python3 -c "import json,sys;print(json.load(sys.stdin)['versions']['$V']['dist']['integrity'])"
# compare that against the tarball you just downloaded before trusting it:
python3 -c "import base64,hashlib,pathlib;print('sha512-'+base64.b64encode(hashlib.sha512(pathlib.Path('/tmp/axe.tgz').read_bytes()).digest()).decode())"
tar -xzf /tmp/axe.tgz -C /tmp package/axe.min.js package/LICENSE package/LICENSE-3RD-PARTY.txt
cp /tmp/package/{axe.min.js,LICENSE,LICENSE-3RD-PARTY.txt} vendor/axe-core/
shasum -a 256 vendor/axe-core/axe.min.js   # update this file and test_vendor.py
```

A version bump can add rules, so expect it to find new violations. That is the point of
pinning: the finding arrives in a deliberate commit rather than on an unrelated Tuesday.
