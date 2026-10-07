# Changelog

All notable changes to this project will be documented in this file.

## [0.11.0] - Unreleased

Payment safety (epic #145).

### Fixed
- Base mainnet USDC payments can now be signed: the EIP-712 domain name for `base` is `"USD Coin"` (the contract's `name()`), not `"USDC"`, which is correct only on Base Sepolia. Tests pin both networks' `DOMAIN_SEPARATOR` to the on-chain values (#126). Must ship together with the gateway fix datafund/swarm_connect#467.

- A paid request that times out, drops or fails with a server error after the payment was sent is no longer reported as a plain failure. It raises `PaymentOutcomeUnknownError`; when the gateway confirms it collected the payment (`X-Payment-Status: settled_not_delivered` or `DELIVERY_FAILED_AFTER_PAYMENT`), `PaymentSettledNotDeliveredError`. The CLI prints the amount, payer, pay-to address, authorization nonce and any `X-Payment-Transaction`, without `-v`, and tells the user not to re-run (#127)
- A 202 `PURCHASE_PENDING` answer to a paid stamp purchase raises `StampPurchasePendingError` with the transaction, stamp label and lookup, instead of a model validation error (#127)
- A second 402 after paying raises `PaymentRejectedError` with the gateway's reason (#127)
- Paid calls (stamp purchase, upload, signed upload, pool acquire, manifest upload) wait 180 s instead of 30–120 s, longer than the gateway's own work after settling (#127)

- The auto-pay limit is a hard cap: with auto-pay on and no confirmation callback, a payment above `x402_max_auto_pay_usd` is refused before signing (it was signed) (#128)
- The payment prompt defaults to No (`[y/N]`), so Enter or a piped newline no longer pays (#128)
- Amounts are shown with all 6 USDC decimals ($0.004 showed as "$0.00"); the prompt shows the payment option's network (not the configured one), the `payTo` address and the asset (#128)

- The 402 payment request is validated before signing: only the `exact` scheme is signed (others were signed as EIP-3009 anyway), an `asset` other than the network's USDC contract is refused, and a malformed amount or `payTo` is refused. Raises `PaymentRequirementsError` listing the reasons (#129)
- The payment prompt leads with the request the CLI made (`POST /api/v1/stamps/`); the gateway's own description is shown after it, cleaned of control characters, truncated and marked as the gateway's (#129)

### Added
- `X402_EXPECTED_PAY_TO` (and `GatewayClient(x402_expected_pay_to=...)` / `X402Client(expected_pay_to=...)`) pins the payment recipient; `x402 status` shows it (#129)
- A warning (`InsecureGatewayWarning` in library use) when x402 is enabled against a plain-http gateway that is not on loopback (#129)
- `--no-x402`, `--no-auto-pay` and `--no-free` flags, which override `X402_ENABLED`, `X402_AUTO_PAY` and `FREE_TIER` for one command (#128)
- A running total of payments sent during a command, shown at the second prompt and after a successful `upload` / `upload-collection` (#128)
- `GatewayClient(x402_on_payment_sent=...)` hook, and payment callbacks that accept an `option` keyword receive the `X402PaymentOption` (#128)
- A 402 option whose `extra` advertises a different EIP-712 `name` or `version` than the USDC contract uses is refused before signing, with a message naming the mismatch (#126)

## [0.8.3] - 2026-03-03

### Added
- `--free` CLI flag and `FREE_TIER` env var for gateway free tier access (sends `X-Payment-Mode: free` header, rate-limited to 3 req/min) (#82)

## [0.8.2] - 2026-03-02

### Added
- `--gas` option on all chain write commands (`anchor`, `access`, `status`, `transfer`, `delegate`, `transform`, `protect`) to set an explicit gas limit, bypassing RPC estimation (#75)
- `CHAIN_GAS_LIMIT` environment variable for persistent gas limit configuration

## [0.8.1] - 2026-03-02

### Fixed
- `chain anchor` now checks if a hash is already registered before sending a transaction, preventing wasted gas and unhelpful revert errors (#76)
- `chain protect --anchor-new` treats already-registered new hash as non-fatal, continuing with transform/restrict steps

### Added
- `DataAlreadyRegisteredError` exception with `data_hash`, `owner`, `timestamp`, `data_type` attributes
- Human-readable and JSON error output for already-registered hashes

## [0.8.0] - 2025-02-25

### Added
- **9 real-world examples** covering upload/download, audit trail, scientific data, batch processing, encrypted data, market memory, stamp management, CI/CD integration, and verification
- **On-chain anchoring** via DataProvenance contract on Base Sepolia (`chain` CLI subcommand)
- Chain commands: `anchor`, `get`, `verify`, `access`, `status`, `transfer`, `delegate`, `transform`, `protect`
- **x402 payment support** for pay-per-request mode (USDC on Base chain)
- x402 commands: `x402 status`, `x402 balance`, `x402 info`
- **Collection/manifest upload** (`upload-collection`) for directories as Swarm manifests
- **Notary signing** (`--sign notary`) and signature verification (`--verify`)
- CI workflow testing Python 3.9-3.13 with blockchain deps matrix
- MIT license

### Changed
- Renamed `SWARM_X402_PRIVATE_KEY` env var to `X402_PRIVATE_KEY` (backwards-compatible fallback preserved)

## [0.5.0] - 2025-01-15

### Added
- Notary signing feature (`--sign notary` on upload, `--verify` on download)
- Notary CLI commands: `notary info`, `notary status`, `notary verify`

## [0.4.0] - 2025-01-10

### Added
- Stamp management commands: `stamps list`, `stamps info`, `stamps extend`, `stamps check`, `stamps pool-status`
- Pool stamp acquisition (`--usePool`) for faster uploads (~5s vs >1min)
- `--stamp-id` option for stamp reuse across multiple uploads
- `--size` presets (small, medium, large) for stamp purchasing
- `--duration` option for custom stamp validity (hours)
- Wallet and chequebook info commands

## [0.3.0] - 2025-01-05

### Added
- Gateway backend as default (no local Bee node required)
- Download command with integrity verification
- Verbose mode (`-v`) for debugging
- Version flag (`--version`)

## [0.2.0] - 2024-12-20

### Added
- Pydantic v2 data models for metadata and API responses
- Custom exception hierarchy
- Environment-based configuration via `.env`

## [0.1.0] - 2024-12-15

### Added
- Initial release
- Upload files to Swarm with provenance metadata wrapping
- SHA-256 content hashing for integrity
- Local Bee node backend support
- CLI with Typer framework
