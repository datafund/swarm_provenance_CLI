# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- `.env` is now found from the folder you run the command in: that folder first, then each parent folder up to the root, and the first `.env` found is used. It was found from the folder the package is installed in, so with the editable install from the README the repository's `.env`, with its keys and auto-pay settings, applied wherever you ran the CLI, and with a virtual environment under your home folder `~/.env` applied. **Behaviour change:** if you kept your settings in the repository's `.env` and run the CLI from other folders, copy that `.env` to the folder you work in, or export the variables. Variables already set in the environment still take precedence over `.env` (#141)
- The x402 signing key is now read the same way by the signer and by `x402 status` / `x402 balance` (`resolve_x402_private_key()`). If `X402_PRIVATE_KEY_ENV` names a variable other than `X402_PRIVATE_KEY`, only that variable is read; otherwise `X402_PRIVATE_KEY` is read, then the legacy `SWARM_X402_PRIVATE_KEY`. Before, `X402_PRIVATE_KEY_ENV` changed only the status display and the signer always read `X402_PRIVATE_KEY`; and a key in `SWARM_X402_PRIVATE_KEY` signed payments while `x402 status` showed "Not set". **Behaviour change:** with `X402_PRIVATE_KEY_ENV` set to another name, a key in `X402_PRIVATE_KEY` is no longer used. `x402 status` names the variable the key came from, never the key. If `X402_PRIVATE_KEY_ENV` is not a valid variable name (letters, digits and `_`, not starting with a digit) or is 32 or more hex digits, with or without `0x`, no key is read, and the signer, `x402 status` and `x402 balance` say "X402_PRIVATE_KEY_ENV is not a valid variable name" without repeating the value. A valid custom name made only of hex digits is used but not printed; messages say "the variable named by X402_PRIVATE_KEY_ENV" instead (#141)
- `X402_RPC_URL` is now used for the x402 USDC balance and EIP-712 domain checks (an explicit `rpc_url` argument to `X402Client` still comes first). It was documented but ignored. Errors that repeat it are redacted like the chain RPC URLs (#141)
- `CHAIN_RPC_URLS` (comma-separated) is now passed to the chain client as the fallback RPC URLs, replacing the preset fallbacks. It was documented but ignored (#141)

### Removed
- Removed the `CHAIN_ENABLED` setting (`config.CHAIN_ENABLED`). It was documented but nothing read it: chain commands always run when you call them (#141)
- Removed `config.X402_PRIVATE_KEY_ENV` and `config.X402_RPC_URL`. The environment variables still work: they are read when used, by `resolve_x402_private_key()` and `X402Client` (#141)

## [0.12.0] - 2026-10-22

### Notes on 0.11.0
- Base mainnet x402 payments need the gateway fix datafund/swarm_connect#467, which advertises `"USD Coin"` as the EIP-712 name for `base`. It is on swarm_connect `main` as of 2026-10-22 (`app/x402/middleware.py`). The production gateway still runs x402 on Base Sepolia. Base mainnet x402 also needs CLI 0.11.0 or later: older versions sign with `"USDC"`, which the Base mainnet USDC contract rejects (#126)
- The 0.11.0 notes say `Idempotency-Key` needs datafund/swarm_connect#422 "on `dev`": it (`app/x402/idempotency.py`) is on swarm_connect `main` too as of 2026-10-21 (#124)

### Fixed
- Gateway errors show the gateway's error code and message. They read `HTTP <status> <CODE>: <message>`, for example `Failed to upload data: HTTP 403 STAMP_OWNERSHIP_DENIED: <message>`, plus `Retry after N s.` when the gateway sends a `Retry-After` header. They used to read `<status> Client Error: <reason> for url: <url>`, which hid codes such as `STAMP_OWNERSHIP_DENIED`, `EXTENSION_TOO_SMALL`, `DAILY_STAMP_ALLOWANCE_EXHAUSTED`, `RATE_LIMIT_EXCEEDED` and `FILE_TOO_LARGE`. Older gateways that send the code only under `detail` are read too, a 422 names the first three invalid fields, and the free-tier 429 adds its specific reason. A response with no readable body (for example a proxy's HTML page) keeps the plain HTTP error. The request URL is no longer in the message; `--verbose` prints it. Gateway text is cleaned of control and invisible formatting characters and shortened before it is shown (#139)
- Failures after a payment name the gateway code: a second 402 reads `The gateway did not accept the payment (PAYMENT_SETTLEMENT_FAILED): <message>`. The gateway's code and message in these errors are cleaned the same way (#139)
- With x402 off, a 402 that carries the gateway's own error code keeps it. The pool's refusal when the free daily allowance is spent (`DAILY_STAMP_ALLOWANCE_EXHAUSTED`, `DAILY_STAMP_ALLOWANCE_PER_CLIENT_EXHAUSTED`; a 402 on gateways where paying bypasses the allowance) now prints the code and the gateway's message, and suggests `--x402` or waiting until the allowance resets. It printed "Payment required but not completed" and suggested `--free`, which draws on the same allowance. `FREE_TIER_DISABLED` and `PAYMENT_REQUIRED` do not suggest `--free` either. A 402 to a request sent with `--free`, such as "Free tier is not available. Payment required." from a gateway with the free tier off, shows the gateway's message and suggests only `--x402`. An ordinary 402 (code `HTTP_402`) without `--free` keeps the old text and the `--free` hint (#139)
- Chain writes (`anchor`, `access`, `status --set`, `transfer`, `delegate`, `transform`, `merge`, `set-storage-ref`, `protect`, and the batch methods) are no longer reported as recorded on a status-1 receipt alone. Each write now requires the contract's own event, emitted by the configured contract address: `DataRegistered`, `StorageRefLinked`, `DataTransformed`, `DataMerged`, `DataAccessed`, `DataStatusChanged`, `DataOwnershipTransferred` or `DelegateAuthorized`. Batch writes require one event per item. When the events are missing, the CLI prints "Not recorded" with the transaction hash and explorer link, and exits 1; with `--json`, it prints an `{"error": "not_recorded", ...}` object. Library callers get the new `TransactionNotRecordedError`. It carries `tx_hash`, `explorer_url`, `contract_address`, `event_name`, and the integers `expected_count` and `emitted_count`. The write did not happen as asked, so a retry is safe once the cause is fixed (#166)
- If the events of a mined transaction cannot be decoded, the write is no longer reported as "Transaction failed". It raises the new `TransactionNotVerifiedError`, which carries the decode error as `reason` and has no `emitted_count`. The write may have happened, so check the transaction before you retry it. The CLI prints "Not verified" with the transaction hash and explorer link (with `--json`, `{"error": "not_verified", ...}`) and exits 1. Both errors subclass the new `TransactionUnconfirmedError(ChainTransactionError)`, so you can catch them together or tell them apart by type (#166)
- `chain protect` and `chain transform --restrict-original` exit 1 when one of their steps is not recorded or not verified; they exited 0 with a warning when the restrict step was affected. They print the transactions of the steps that were recorded. With `--json`, they print the completed steps, `"partial_failure"` (true only if an earlier step was recorded), and an `"unconfirmed"` object whose `"error"` is `"not_recorded"` or `"not_verified"`; `protect --json` printed nothing on stdout when the transform step failed after the new hash was anchored (#166)
- Before the first write, the client reads the code at the configured contract address once (`eth_getCode`), for `anchor` before its duplicate check. If there is no code, it raises `ChainConfigurationError` before anything is signed or sent; a transaction to such an address succeeded and recorded nothing. The check uses the checksummed address, so a lowercase `--contract` works. Only an RPC failure is reported as `ChainConnectionError`, with the RPC URL; this includes an answer that is not JSON-RPC, such as an HTML error page (#166)
- `chain protect` and `chain transform --restrict-original` now handle every failed step the same way: a revert, a failed transaction, insufficient funds, a connection error, or a write that is not recorded or not verified. **Behavior change:** a failed restrict step exited 0 with a warning; it now exits 1, in text and `--json` mode. With `--json`, an insufficient-funds failure in any step of these commands is now reported inside the composite object, as `"error": {"error": "insufficient_funds", ...}`, instead of the standalone top-level object. With `--restrict-original`, a failure in the transform step is now reported in the composite format, and a connection error no longer prints the RPC URL. In text mode, the commands print the transaction hash and explorer link of each completed step before the error. They keep the manual restrict command and the insufficient-funds advice. With `--json`, both commands print the same keys: the step results (`"anchor"` only when it was recorded, `"transform"`, `"restrict"`), `"partial_failure"` (true only if an earlier step was recorded), `"failed_step"`, and either `"unconfirmed"` for a write that is not recorded or not verified, or `"error"` for any other failure. The `"error"` object has an `"error"` type (`"transaction_failed"`, `"insufficient_funds"`, `"connection_failed"` or `"chain_error"`) and a `"message"`. A `"transaction_failed"` error also has a `"tx_hash"`, which is null when nothing was sent; an `"insufficient_funds"` error has the wallet, balance and cost fields of the standalone insufficient-funds output instead of a message. With `--json`, the checks before the first write are reported in the same format; they printed only text. `protect` reports them with `"failed_step": "verify"` and an `"error"` of `"not_registered"` or `"not_active"` (with the record's `"status"`). `transform --restrict-original` reports an unregistered original with `"failed_step": "transform"` and `"not_registered"`. A successful `transform --restrict-original --json` now also prints `"partial_failure": false`. Before this fix, when the transform step of `protect --json` failed after the new hash was anchored, the anchor transaction hash was lost: most errors printed nothing on stdout, and an insufficient-funds error printed only the funds object. `transform` without `--restrict-original` is unchanged (#175)
- A contract revert or RPC failure while a write builds its transaction is no longer raised as a raw web3 exception. Building the transaction runs `eth_estimateGas`, before anything is signed or sent. The CLI printed a traceback, and `protect` and `transform --restrict-original` lost the hashes of the completed steps. Every write (`anchor`, `anchor_for`, `batch_anchor`, `set_storage_ref`, `transform`, `access`, `batch_access`, `set_status`, `batch_set_status`, `transfer_ownership`, `set_delegate`, `merge_transform`) now raises `InsufficientFundsError` when the RPC reports insufficient funds. A revert raises `ChainTransactionError` with the revert reason and no `tx_hash`. A JSON-RPC error answer, such as "nonce too low", raises `ChainTransactionError` ("The RPC rejected the transaction: nonce too low"), because the node was reached. The message shows only the node's error message, not the whole JSON-RPC error object. Only a transport failure (no connection, a timeout including web3's `RequestTimedOut`, or an answer that is not JSON-RPC) raises `ChainConnectionError`. Any other error while building raises `ChainTransactionError` ("Could not build the transaction: ..."). When sending a transaction fails before it is mined, the `ChainTransactionError` message is now only the error's reason, for example "execution reverted: Not owner". It was "Transaction failed: <error>", which the CLI printed as "ERROR: Transaction failed: Transaction failed: ...", and for a revert the error was web3's (message, data) tuple with the raw revert data. A revert is no longer reported as `InsufficientFundsError` when its reason contains "insufficient funds". `anchor` still reports an "already registered" revert during gas estimation as `DataAlreadyRegisteredError` (#175)
- `import swarm_provenance_uploader.chain.provider` (or `core.chain_client`, `chain.exceptions`) failed with a circular `ImportError` (cannot import `ChainError`) unless `swarm_provenance_uploader.exceptions` was imported first; `import swarm_provenance_uploader.chain` on its own set `BLOCKCHAIN_AVAILABLE = False` even with web3 installed. The chain exceptions are now re-exported from `swarm_provenance_uploader.exceptions` lazily
- Chain errors no longer show the RPC URL's path, query or `user:password`, where providers such as Alchemy, Infura and QuickNode put the API key. The scheme, host and port stay, so `https://base-sepolia.g.alchemy.com/v2/<key>` is shown as `https://base-sepolia.g.alchemy.com/…`. The HTTP status and error text stay too, for example `401 Client Error: Unauthorized`. This covers the `RPC URL:` line, the error messages (including the contract code check), the `"reason"` field of `--json` output, and warnings and log lines that repeat an RPC error. When a `ChainError` is created, its own message, `ChainConnectionError.rpc_url` and `TransactionNotVerifiedError.reason` are redacted, so library callers get the same text. Raw `requests` and web3 exceptions that `ChainClient` read methods (`get`, `verify`, `balance`, `get_by_storage_ref`, `get_provenance_chain`) let through to library callers, and the original exception that a `ChainError` keeps as `__cause__`, are not redacted yet; a follow-up issue tracks this. URLs with any scheme are redacted, also a misspelled one such as `htps://`, and so is the URL that requests quotes in "No connection adapters were found for '...'" and "Invalid URL '...'", also without a scheme. `ChainProvider` also registers the path, query, fragment and `user:password` of each configured RPC URL (primary and fallbacks) when they are at least 8 characters long, with their percent-encoded, decoded and HTML-escaped forms. The last path segment, and the values of query parameters named like a credential (`key`, `apikey`, `api_key`, `api-key`, `token`, `access_token`, `accesstoken`, `dkey`, `auth`, `secret`, `password`), are registered too when they are at least 8 characters long, so a short key is removed even when the server echoes only the key. Other path segments and query values are registered only when they look like a key: at least 16 characters, or at least 8 characters with both a letter and a digit. Query keys, chain names and strings from the chain presets are never registered, so a dRPC URL such as `https://lb.drpc.live/base-sepolia/<key>` does not cut `base-sepolia` out of other messages. These strings are replaced wherever an error text repeats them, for example when the RPC answers with an HTML page that says "The requested URL /v2/<key> was not found". New helpers `redact_url()`, `redact_urls()` and `register_url_secrets()` are in `swarm_provenance_uploader.chain.redact` (#169)
- A `chain` command that hits an RPC error no handler catches, such as an HTTP 401 or a refused connection during `chain get`, `verify`, `lookup` or `balance`, now exits 1 with `ERROR: Cannot connect to chain: ...` and the redacted error text. It ended in a traceback that showed the full RPC URL and local variables. A JSON-RPC error answer from the node, such as "nonce too low", is reported as `ERROR: The RPC rejected the request: <message>`, not as a connection failure. The contract code check reports such an answer the same way: it raises `ChainConfigurationError` ("The RPC rejected the contract code check: <message>") instead of `ChainConnectionError`. A transport failure or timeout is still a `ChainConnectionError`. Other unexpected errors in `chain` commands exit 1 with `ERROR: Chain command failed: ...`. With `-v`, these errors also print the traceback to stderr, without local variables and with URLs redacted (#169)
- The `RPC URL:` line of a chain connection error is printed to stderr with the error, so it no longer mixes into `--json` output on stdout. The same applies to the other lines that go with a chain error: `Install with: ...` and `Check PROVENANCE_WALLET_KEY ...` when the chain client cannot be created, the `Anchor it first` hints of `transform`, `protect` and `merge`, the `Hash:` line of `merge`'s not-registered error, `merge`'s `Usage:` line, and the `Transaction:` line after "Transaction failed". With `--json`, stdout is now empty or valid JSON in these cases (#169)

### Added
- `GatewayHTTPError`, a subclass of `requests.exceptions.HTTPError` that keeps `.response` and adds `status_code`, `code`, `gateway_message` and `retry_after`. The public `GatewayClient` methods still wrap it, as before, in `ConnectionError`, `PoolAcquisitionError` or a similar error, so library callers reach it as `e.__cause__` of that error (#139)
- `PaymentRequiredError` has the optional attributes `code`, `gateway_message`, `resets_at` and `free_tier_used`, and the property `free_tier_helps` (#139)

### Changed
- `requires-python` is `>=3.9` (was `>=3.8`); CI tests 3.9 to 3.13
- The `x402` and `blockchain` extras cap web3 below the next major version: `web3>=7.0.0,<9`
- `project.license` is the SPDX expression `"MIT"` with `license-files`, which clears the setuptools deprecation warning on build; building needs setuptools 77 or later

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
