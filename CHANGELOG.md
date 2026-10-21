# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- Chain writes (`anchor`, `access`, `status --set`, `transfer`, `delegate`, `transform`, `merge`, `set-storage-ref`, `protect`, and the batch methods) are no longer reported as recorded on a status-1 receipt alone. Each write now requires the contract's own event, emitted by the configured contract address: `DataRegistered`, `StorageRefLinked`, `DataTransformed`, `DataMerged`, `DataAccessed`, `DataStatusChanged`, `DataOwnershipTransferred` or `DelegateAuthorized`. Batch writes require one event per item. When the events are missing, the CLI prints "Not recorded" with the transaction hash and explorer link, and exits 1; with `--json`, it prints an `{"error": "not_recorded", ...}` object. Library callers get the new `TransactionNotRecordedError`. It carries `tx_hash`, `explorer_url`, `contract_address`, `event_name`, and the integers `expected_count` and `emitted_count`. The write did not happen as asked, so a retry is safe once the cause is fixed (#166)
- If the events of a mined transaction cannot be decoded, the write is no longer reported as "Transaction failed". It raises the new `TransactionNotVerifiedError`, which carries the decode error as `reason` and has no `emitted_count`. The write may have happened, so check the transaction before you retry it. The CLI prints "Not verified" with the transaction hash and explorer link (with `--json`, `{"error": "not_verified", ...}`) and exits 1. Both errors subclass the new `TransactionUnconfirmedError(ChainTransactionError)`, so you can catch them together or tell them apart by type (#166)
- `chain protect` and `chain transform --restrict-original` exit 1 when one of their steps is not recorded or not verified; they exited 0 with a warning when the restrict step was affected. They print the transactions of the steps that were recorded. With `--json`, they print the completed steps, `"partial_failure"` (true only if an earlier step was recorded), and an `"unconfirmed"` object whose `"error"` is `"not_recorded"` or `"not_verified"`; `protect --json` printed nothing on stdout when the transform step failed after the new hash was anchored (#166)
- Before the first write, the client reads the code at the configured contract address once (`eth_getCode`), for `anchor` before its duplicate check. If there is no code, it raises `ChainConfigurationError` before anything is signed or sent; a transaction to such an address succeeded and recorded nothing. The check uses the checksummed address, so a lowercase `--contract` works. Only an RPC failure is reported as `ChainConnectionError`, with the RPC URL; this includes an answer that is not JSON-RPC, such as an HTML error page (#166)
- `chain protect` and `chain transform --restrict-original` now handle every failed step the same way: a revert, a failed transaction, insufficient funds, a connection error, or a write that is not recorded or not verified. **Behavior change:** a failed restrict step exited 0 with a warning; it now exits 1, in text and `--json` mode. With `--json`, an insufficient-funds failure in any step of these commands is now reported inside the composite object, as `"error": {"error": "insufficient_funds", ...}`, instead of the standalone top-level object. With `--restrict-original`, a failure in the transform step is now reported in the composite format, and a connection error no longer prints the RPC URL. In text mode, the commands print the transaction hash and explorer link of each completed step before the error. They keep the manual restrict command and the insufficient-funds advice. With `--json`, both commands print the same keys: the step results (`"anchor"` only when it was recorded, `"transform"`, `"restrict"`), `"partial_failure"` (true only if an earlier step was recorded), `"failed_step"`, and either `"unconfirmed"` for a write that is not recorded or not verified, or `"error"` for any other failure. The `"error"` object has an `"error"` type (`"transaction_failed"`, `"insufficient_funds"`, `"connection_failed"` or `"chain_error"`) and a `"message"`. A `"transaction_failed"` error also has a `"tx_hash"`, which is null when nothing was sent; an `"insufficient_funds"` error has the wallet, balance and cost fields of the standalone insufficient-funds output instead of a message. With `--json`, the checks before the first write are reported in the same format; they printed only text. `protect` reports them with `"failed_step": "verify"` and an `"error"` of `"not_registered"` or `"not_active"` (with the record's `"status"`). `transform --restrict-original` reports an unregistered original with `"failed_step": "transform"` and `"not_registered"`. A successful `transform --restrict-original --json` now also prints `"partial_failure": false`. Before this fix, when the transform step of `protect --json` failed after the new hash was anchored, the anchor transaction hash was lost: most errors printed nothing on stdout, and an insufficient-funds error printed only the funds object. `transform` without `--restrict-original` is unchanged (#175)
- A contract revert or RPC failure while a write builds its transaction is no longer raised as a raw web3 exception. Building the transaction runs `eth_estimateGas`, before anything is signed or sent. The CLI printed a traceback, and `protect` and `transform --restrict-original` lost the hashes of the completed steps. Every write (`anchor`, `anchor_for`, `batch_anchor`, `set_storage_ref`, `transform`, `access`, `batch_access`, `set_status`, `batch_set_status`, `transfer_ownership`, `set_delegate`, `merge_transform`) now raises `InsufficientFundsError` when the RPC reports insufficient funds. A revert raises `ChainTransactionError` with the revert reason and no `tx_hash`. A JSON-RPC error answer, such as "nonce too low", raises `ChainTransactionError` ("The RPC rejected the transaction: ..."), because the node was reached. Only a transport failure (no connection, a timeout, or an answer that is not JSON-RPC) raises `ChainConnectionError`. `anchor` still reports an "already registered" revert during gas estimation as `DataAlreadyRegisteredError` (#175)

## [0.11.0] - 2026-10-21

Payment safety (epic #145).

### Fixed
- `download` no longer reports "Download and verification successful": its check compares the document's data with the document's own `content_hash`, both from the same response, and never against the requested Swarm reference. The output now says what was checked, which notary (pinned or the serving gateway's) signed the data, and that a notary signature, even a pinned one, does not tie the data to the reference. The full check is still open in #134 (#134)
- `download` enforces notary signatures: a signature that does not verify, or cannot be checked (no expected address, eth-account missing), exits 1 and saves nothing; it ended in "Download and verification successful" with exit 0. `--strict` with a stripped signature passed; `--strict` now also requires a signature. The saved `.meta.json` keeps `signatures`, so it can be re-verified (#135)
- `download` refuses a reference that is not 64 or 128 hex characters before using it as a file name or URL path; `download ../x` wrote outside `--output-dir`. A `0x` prefix is accepted and dropped. `--stamp-id` is checked the same way (64 hex) (#132)
- `ChainProvider.health_check` and `get_block_number` try each RPC URL at most once per call; two endpoints that connect but fail the check (e.g. wrong chain) were switched between until the recursion limit, and a dead fallback was probed repeatedly (#132)
- Base mainnet USDC payments can now be signed: the EIP-712 domain name for `base` is `"USD Coin"` (the contract's `name()`), not `"USDC"`, which is correct only on Base Sepolia. Tests pin both networks' `DOMAIN_SEPARATOR` to the on-chain values (#126). Must ship together with the gateway fix datafund/swarm_connect#467.
- A paid request that times out, drops, is interrupted (Ctrl-C) or fails with a server error after the payment was sent is no longer reported as a plain failure. It raises `PaymentOutcomeUnknownError`; when the gateway confirms it collected the payment (`X-Payment-Status: settled_not_delivered`, `DELIVERY_FAILED_AFTER_PAYMENT`, or a success answer the CLI cannot read), `PaymentSettledNotDeliveredError`. The CLI prints the amount, payer, pay-to address, authorization nonce, until when the authorization can be collected, and any `X-Payment-Transaction`, without `-v`, and tells the user not to re-run (#127)
- A 202 `PURCHASE_PENDING` answer to a paid stamp purchase raises `StampPurchasePendingError` with the transaction and stamp label, instead of a model validation error (#127)
- A second 402 after paying raises `PaymentRejectedError` with the gateway's reason (#127)
- Paid calls (stamp purchase, upload, signed upload, pool acquire, manifest upload) use a 10 s connect / 240 s read timeout instead of 30–120 s, longer than the gateway's own work after settling (#127)
- The auto-pay limit is a hard cap: with auto-pay on and no confirmation callback, a payment above `x402_max_auto_pay_usd` is refused before signing (it was signed). The comparison is exact (#128)
- The payment prompt defaults to No (`[y/N]`): Enter, a piped newline or a closed stdin no longer pays (#128)
- Amounts are shown with all 6 USDC decimals ($0.004 showed as "$0.00"); the prompt shows the payment option's network (not the configured one), the `payTo` address and the asset (#128)
- Declining or exceeding the limit with x402 enabled no longer says "Use --x402 to enable x402 payments" (#128)
- The 402 payment request is validated before signing: only the `exact` scheme is signed (others were signed as EIP-3009 anyway), an `asset` other than the network's USDC contract is refused, and a malformed amount or `payTo` (or the zero address) is refused. Raises `PaymentRequirementsError` listing the reasons (#129)
- The payment prompt leads with the request the CLI made (`POST /api/v1/stamps/`); the gateway's own description is shown after it, cleaned of control and invisible formatting characters, truncated and marked as the gateway's (#129)
- The full stamp ID is printed after a purchase or pool acquisition (it was cut to the last 12 characters without `-v`), and if the command then fails (stamp never usable, upload error, unknown payment outcome), the ID is repeated with a `--stamp-id` hint so a retry does not buy another stamp. With `-v`, `upload-collection` no longer prints a separate `Stamp ID:` line (#130)

### Added
- `download` on the local backend checks the content against the Swarm reference, chunk by chunk (`core/swarm_verify.py`): each chunk from the Bee node is checked against its address, the manifest is followed to the file, and the rebuilt file is compared with the download; a mismatch exits 1 and saves nothing. `--no-verify-reference` skips it; an explicit `--verify-reference` fails (exit 1) where the check cannot run (gateway backend, encrypted reference). The manifest is resolved exactly as Bee serves `/bzz` (path cleaning, value node; feed manifests and encrypted references are not checked, the latter with a note). Checked live against Bee 2.8.2 for redundancy levels 0–4 and sizes up to two-level trees; the unit tests use chunks recorded from that node plus crafted trees and manifests. The gateway backend needs a chunk endpoint first (datafund/swarm_connect#499) (#134)
- `download --require-signature` fails when the document has no notary signature; `--notary-address` / `NOTARY_ADDRESS` pins the expected notary instead of trusting the serving gateway's `/notary/info` (one pin for all gateways; `notary verify --address` reads it too) (#135)
- `Idempotency-Key` on paid requests (#124): one key per command (`GatewayClient(idempotency_key=...)`; a fresh key per paid operation otherwise), the same on every attempt. The CLI waits and retries on `IDEMPOTENCY_KEY_IN_PROGRESS` (honouring `Retry-After`, at least 5 s) and `IDEMPOTENCY_UNAVAILABLE`, resending the same authorization (the gateway releases it) and signing a new one only after an attempt that got no answer, at most 3 per request; and stops on `IDEMPOTENCY_KEY_SETTLEMENT_UNKNOWN` (prints the original nonce), `IDEMPOTENCY_KEY_SETTLED_PENDING` (prints the transaction) and `IDEMPOTENCY_KEY_DELIVERED_NOT_STORED` (reported as a success, exit 0 when it is the last step). `IDEMPOTENCY_KEY_REUSED` / `INVALID` say the key handling is at fault, not the input. New `--idempotency-key` repeats a failed run with its key. Needs a gateway with datafund/swarm_connect#422 (on `dev`; harmless but without effect elsewhere)
- `stamps list --full` shows complete stamp IDs and labels; `stamps list --wallet <address>` lists the stamps that wallet bought (needs x402 enabled on the gateway). The default output now ends with a note that IDs are shortened, and its columns line up (#130)
- A note when `--usePool`, `--size`, `--duration`, `--depth` or `--amount` is ignored because `--stamp-id` was given (#130)
- `--no-x402`, `--no-auto-pay` and `--no-free` flags, which override `X402_ENABLED`, `X402_AUTO_PAY` and `FREE_TIER` for one command (#128)
- A running total of payments sent during a command, shown at the second prompt and at the end of the command, also when it fails (#128)
- `GatewayClient(x402_on_payment_sent=...)` hook; a payment callback with a parameter named `option` receives the `X402PaymentOption` (#128)
- `X402_EXPECTED_PAY_TO` (and `GatewayClient(x402_expected_pay_to=...)` / `X402Client(expected_pay_to=...)`) pins the payment recipient; `x402 status` shows it (#129)
- A warning (`InsecureGatewayWarning` in library use) when x402 is enabled against a plain-http gateway that is not on loopback (#129)
- A 402 option whose `extra` advertises a different EIP-712 `name` or `version` than the USDC contract uses is refused before signing, with a message naming the mismatch (#126)


### Changed
- CI runs on `main` and `development`, installs the `x402` and `blockchain` extras, runs unit tests only (`-m "not integration"`), and reports one `CI passed` check to require on protected branches (#132)
- The example demos in `tests/test_examples.py` that upload to a live gateway run only with `RUN_LIVE_TESTS=1`; CI's unit job uploaded to the production gateway (#132)
- `typer` is pinned below 0.23 (0.23+ needs click 8.2, which the click pin excludes, and newer versions broke the CLI tests) (#132)
- The `x402` extra no longer installs the unused `x402` SDK package; it needs Python 3.10+, which made the extra uninstallable on 3.9 (#132)
- CI runs a secret scan (gitleaks 8.30.1, pinned and checksum-verified) on the checked-out files and on the commits each push or pull request adds (for a new branch or a force-push: every commit no other branch has), and fails `CI passed` on a finding or when it scans nothing it should have. `.gitleaks.toml` adds a rule for raw Ethereum private keys (including `--private-key 0x…` and `*_PK=` forms) and allowlists the rotated #131 leak commit; `.claude/settings.local.json` and `.env.*` (except `.env.example`) are ignored (#131)
- Install instructions no longer name a PyPI package: the package is not published there, so `pip install swarm-provenance-uploader` would install whatever someone registers under that name. The CI templates in `examples/08-ci-cd-integration/` install from this repository at a pinned reference (`SWARM_PROV_CLI_REF`: a release tag from v0.11.0, or a commit SHA; older tags do not build), and the "dependencies not installed" messages name the dependencies to install (#133)
- The `x402` and `blockchain` extras require `web3>=7.0.0` and `eth-account>=0.13.5`, the versions the code needs (`sign_typed_data`, `raw_transaction`); the old floors (web3 6, eth-account 0.8/0.10) installed versions that fail at signing (#133)
- One version source: `pyproject.toml` reads the version from `__version_base__` in `swarm_provenance_uploader/__init__.py` (#133)
- `typer>=0.12,<0.23` instead of `typer[all]`: the `all` extra no longer exists; 0.12+ includes what it added (#133)
- `download` fails (exit 1) on a notary signature that does not verify or cannot be checked: also for a signed document on the local backend without `--notary-address`, from a gateway with notary disabled, without eth-account installed, or with a malformed `signatures` field. Use `--no-verify` to download without checking; combining it with `--require-signature` / `--strict` is an error (#135)
- Library users: `GatewayClient.download_data` and `swarm_client.download_data_from_swarm` raise `ValueError` for a reference that is not 64/128 hex characters (including a `0x` prefix), and `get_stamp` / `extend_stamp` / `check_stamp_health` for a stamp ID that is not 64 hex (#132)
- Library users: after a payment was sent, timeouts, 5xx answers and a second 402 now raise `X402Error` subclasses (`PaymentOutcomeUnknownError`, `PaymentSettledNotDeliveredError`, `PaymentRejectedError`), no longer the builtin `ConnectionError`. Code catching `ConnectionError` around paid `GatewayClient` calls should also catch `X402Error` (#127)

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
