# scheMAGIC Stripe Edge Case Harness

Automated test harness for the 85-case Stripe edge plan at `Projects/schemagic/Stripe Test Plan.md` (vault).

## Quick start (localhost)

```bash
# From repo root
source .venv-tests/bin/activate

# Terminal 1: Next.js dev
cd web && npm run dev

# Terminal 2: tests (sidecar is spawned by conftest)
cd ../
pytest tests/stripe/ --env=local -v
```

Webhook tests use synthetic HMAC-signed POSTs — no Stripe CLI required.

## Environments

| Flag | Target | Webhooks |
|------|--------|----------|
| `--env=local` | http://localhost:3000 | Synthetic (signed with STRIPE_WEBHOOK_SECRET from pass) |
| `--env=preview` | $VERCEL_PREVIEW_URL | Endpoint registered programmatically |
| `--env=prod` | https://schemagic.design | Existing prod endpoint; test-DELETEME- emails only |

## Credentials

All pulled from `pass` at fixture startup. Required paths:
- `schemagic/stripe-secret-key` (sk_test_...)
- `schemagic/stripe-price-id`
- `schemagic/stripe-webhook-secret`
- `schemagic/license-private-key`
- `schemagic/license-public-key`

## Running subsets

```bash
pytest tests/stripe/phase1_identity.py --env=local           # one phase
pytest tests/stripe/ -m "not ux and not slow" --env=local   # skip UX + slow
pytest tests/stripe/ --ux --env=local                        # include Playwright
pytest tests/stripe/phase11_smoke.py --env=prod              # prod smoke only
```

## Results

After a run: markdown table written to `results/run-YYYYMMDD-HHMMSS.md` and appended to the vault test plan under "Test Runs".

## Cleanup

```bash
python tests/stripe/cleanup.py   # sweeps test-DELETEME-* orphans
```
