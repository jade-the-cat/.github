# `.github`

Organization-level defaults for [jade-the-cat](https://github.com/jade-the-cat).

- **`profile/README.md`** — the public org profile, rendered at <https://github.com/jade-the-cat>.
- **Community health defaults** — `CONTRIBUTING.md`, `SECURITY.md`, and the issue / PR templates
  apply to **every repo in the org** that doesn't define its own.
- **`.github/workflows/`** — reusable workflows other repos call, pinned by commit, e.g.
  `uses: jade-the-cat/.github/.github/workflows/secret-scan.yml@<sha> # main YYYY-MM-DD`.
- **`actions/`** — composite actions those workflows use, tested by `actions-ci.yml`.
  `actions/vendor-freshness` holds a vendored copy (brand tokens, logos, the twin rig) to its
  provenance record; the record format is documented in
  [`vendor_freshness/provenance.py`](actions/vendor-freshness/vendor_freshness/provenance.py).

> This repo must stay **public** for the profile and default templates to take effect, so it
> holds no secrets and nothing private: consumers pass their own secrets to the workflows.
