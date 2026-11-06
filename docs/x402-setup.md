# x402 payment setup guide

This guide walks you through setting up x402 payments for the Swarm Provenance CLI.

> **Alpha software, real money.** The CLI's default gateway, `https://provenance-gateway.datafund.io`, charges real USDC on Base mainnet. The software comes with no guarantees, and refunds should not be expected. Spend small amounts, and test on the staging gateway or the free tier first (see [Production vs staging](#production-vs-staging)). Send feedback to info@datafund.io.

## What is x402?

x402 is a payment protocol that uses HTTP 402 "Payment Required" responses to enable pay-per-request APIs. When the gateway requires payment for an operation, it returns a 402 response with payment options. The CLI signs a USDC payment using your wallet and retries the request.

**Key features:**
- Pay-per-request model (no subscriptions)
- USDC stablecoin on Base chain
- EIP-712 signed messages: you only sign, and the facilitator submits the transfer and pays the gas, so the wallet needs USDC but no ETH
- A staging gateway that takes test USDC on Base Sepolia, for testing

### How it works

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          x402 Payment Flow                                    │
└──────────────────────────────────────────────────────────────────────────────┘

   Your CLI                         Gateway                      Blockchain
      │                                │                              │
      │  1. Request (stamp purchase)   │                              │
      │──────────────────────────────>│                              │
      │                                │                              │
      │  2. HTTP 402 Payment Required  │                              │
      │<──────────────────────────────│                              │
      │     { accepts: [{              │                              │
      │         network: "base-sepolia"│                              │
      │         amount: "50000"        │                              │
      │         payTo: "0x..."         │                              │
      │       }]                       │                              │
      │     }                          │                              │
      │                                │                              │
      │  3. Sign EIP-712 message       │                              │
      │  (offline, no gas needed)      │                              │
      │                                │                              │
      │  4. Retry with X-PAYMENT       │                              │
      │──────────────────────────────>│                              │
      │     { signature: "0x...",      │                              │
      │       from: "0x...",           │                              │
      │       to: "0x...",             │                              │
      │       amount: "50000" }        │                              │
      │                                │                              │
      │                                │  5. Verify & execute         │
      │                                │  TransferWithAuthorization   │
      │                                │─────────────────────────────>│
      │                                │                              │
      │                                │  6. USDC transferred         │
      │                                │<─────────────────────────────│
      │                                │                              │
      │  7. HTTP 201 Created           │                              │
      │<──────────────────────────────│                              │
      │     { batchID: "abc123..." }   │                              │
      │                                │                              │
```

**Key points:**
- Step 3 is done locally - no gas is required for signing
- USDC uses 6 decimals, so "50000" = $0.05
- The signature authorizes a one-time USDC transfer
- If you decline payment, the request fails with PaymentRequiredError

## Prerequisites

- Python 3.9+
- An Ethereum wallet (MetaMask, hardware wallet, etc.)
- USDC on the network of the gateway you use: test USDC on Base Sepolia for the staging gateway, or real USDC on Base mainnet for the default gateway. No ETH is needed; the facilitator pays the gas.

## Step 1: Install x402 dependencies

Install the CLI with x402 support:

```bash
pip install -e .[x402]
```

This installs:
- `eth-account` - Ethereum account management and signing
- `web3` - Blockchain interaction
- `x402` - x402 protocol library

## Step 2: Create or export a wallet

### Option A: Use an existing wallet

Export your private key from MetaMask or another wallet. **Be careful with private keys!**

In MetaMask:
1. Click the three dots menu
2. Go to Account Details
3. Click "Export Private Key"
4. Enter your password
5. Copy the private key (starts with 0x)

### Option B: Create a new wallet

```python
from eth_account import Account
account = Account.create()
print(f"Address: {account.address}")
print(f"Private key: {account.key.hex()}")
```

**Important:** Store your private key securely. Never commit it to version control.

## Step 3: Choose a gateway and fund the wallet

Read [Production vs staging](#production-vs-staging) first. In short: to test, use the staging gateway with test USDC; to pay on the default gateway, fund the wallet with a small amount of real USDC on Base mainnet.

### Testing on the staging gateway (test USDC)

Test USDC works only with the staging gateway. Point the CLI at it:

```bash
PROVENANCE_GATEWAY_URL=https://provenance-gateway.dev.datafund.io
X402_NETWORK=base-sepolia   # the default
```

Get test USDC:

1. Go to https://faucet.circle.com/
2. Select "Base Sepolia" network
3. Enter your wallet address
4. Request test USDC

The USDC contract on Base Sepolia is: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`. No test ETH is needed.

## Step 4: Configure the CLI

### Private key

The CLI reads the payment key from the `X402_PRIVATE_KEY` environment variable (or the variable that `X402_PRIVATE_KEY_ENV` names; see the lookup order below). Do not type the key into your shell, for example with `export X402_PRIVATE_KEY=0x...`: it stays in your shell history. Instead, read it from your password manager's command-line tool (such as 1Password `op read`, `pass`, or macOS `security`) into the variable for one command:

```bash
X402_PRIVATE_KEY="$(op read 'op://<vault>/<item>/<field>')" swarm-prov-upload x402 status
```

The same form works for any command, for example `swarm-prov-upload --x402 upload --file data.txt`. If you must keep the key in a `.env` file, make the file readable only by you (`chmod 600 .env`) and never commit it. Use a dedicated wallet that holds only what you plan to spend.

### Environment variables

Add to your `.env` file:

```bash
# Enable x402 payments
X402_ENABLED=true

# Wallet private key: not stored here, see "Private key" above

# Network: base-sepolia (test USDC; the staging gateway) or base (real USDC;
# the default gateway). The CAIP-2 ids eip155:84532 and eip155:8453 also work.
X402_NETWORK=base-sepolia

# Optional: the staging gateway, for testing with test USDC
# PROVENANCE_GATEWAY_URL=https://provenance-gateway.dev.datafund.io

# Optional: Auto-pay without prompts
X402_AUTO_PAY=false

# Optional: Maximum auto-pay amount per request in USD (a finite number of 0 or more)
X402_MAX_AUTO_PAY_USD=1.00

# Optional: Only pay this recipient (the gateway operator's published pay-to address)
X402_EXPECTED_PAY_TO=0x...

# Optional: Custom RPC for the USDC balance and EIP-712 domain checks
# X402_RPC_URL=https://your-rpc-provider.com
```

`X402_RPC_URL` applies whichever `X402_NETWORK` is selected, the same way `CHAIN_RPC_URLS` does. If you switch networks, change the URL too.

The CLI reads the `.env` of the folder you run it in, or the nearest `.env` in a parent folder. Variables already set in your environment take precedence.

The key is looked up in this order, for both signing and `x402 status`:

1. If `X402_PRIVATE_KEY_ENV` names another variable, only that variable. If it is not a valid variable name, or it contains a run of 32 or more hex digits (it looks like a key), no key is read at all, and the CLI says "X402_PRIVATE_KEY_ENV is not a valid variable name" without repeating the value.
2. Otherwise `X402_PRIVATE_KEY`.
3. Otherwise the legacy `SWARM_X402_PRIVATE_KEY`.

Spaces and line breaks around the key are removed. A variable that is empty or blank counts as not set.

### Verify configuration

```bash
# Check x402 status
swarm-prov-upload x402 status

# Check your USDC balance
swarm-prov-upload x402 balance
```

## Step 5: Make a payment

### Interactive mode (default)

When x402 is enabled and a request requires payment, you'll see a confirmation prompt:

```bash
swarm-prov-upload --x402 upload --file data.txt
```

Output:
```
Payment required: $0.050000 USDC
  For:     POST /api/v1/stamps/ (gateway says: "Postage stamp purchase (depth 17, 25h)")
  Network: base-sepolia
  Pay to:  0x1234567890AbcdEF1234567890aBcDeF12345678
  Asset:   USDC 0x036CbD53842c5426634e7929541eC2318f3dCF7e
Pay now? [y/N]: y
Processing payment...
```

The prompt shows the exact amount (all 6 USDC decimals), the network, the recipient and the token from the gateway's payment request. It defaults to **No**: pressing Enter, a newline piped into the command, or no input at all (closed stdin) declines. `upload` can ask twice (stamp, then upload); the second prompt shows what was already sent in this command, and the success message prints the total.

### Auto-pay mode

Skip prompts for payments under your configured limit:

```bash
# Enable auto-pay for this command
swarm-prov-upload --x402 --auto-pay --max-pay 1.00 upload --file data.txt

# Or set in environment
export X402_AUTO_PAY=true
export X402_MAX_AUTO_PAY_USD=1.00

# Turn it off for one command even if X402_AUTO_PAY=true
swarm-prov-upload --x402 --no-auto-pay upload --file data.txt
```

The limit is per payment. A payment above it is never signed automatically: the CLI asks instead, and library use without a confirmation callback refuses it before signing. `--no-x402` and `--no-free` likewise override `X402_ENABLED` and `FREE_TIER` for one command.

### Retries and Idempotency-Key

Every paid request carries an `Idempotency-Key` header: one random key per command, the same for each attempt. A gateway that supports the key charges at most one attempt; a retry is answered from the first request's result. A retry resends the same payment signature, except after an attempt that got no answer (it may be in use), when a new one is signed; at most 3 signatures are made per request.

- While the first request is still running (`IDEMPOTENCY_KEY_IN_PROGRESS`) or the gateway cannot check keys for a moment (`IDEMPOTENCY_UNAVAILABLE`), the CLI waits and retries with the same key on its own.
- It stops, and does not retry, when the gateway says the first request:
  - may or may not have been collected: it prints the original authorization nonce to check on-chain;
  - was paid but has no result: it prints the transaction to give the operator;
  - succeeded but its result was too large to keep: this is reported as a success.
- A timeout is retried automatically only after the gateway has answered with one of these codes in the same command. Before that the CLI cannot tell whether the gateway supports the key, so it reports the payment instead (see below).

When a command fails with an unknown payment outcome, the error shows its key and the command line to repeat it with. `--idempotency-key` is a global option, so it goes before the command (`swarm-prov-upload --idempotency-key <key> upload ...`). That re-run repeats the same requests with the same key: on a gateway that supports it, an operation that already went through is answered from its result instead of being charged again. On a gateway without support (the header is ignored), that re-run pays again, so check the payment first as described below.

Gateway support: datafund/swarm_connect has it on `dev` (staging) and not yet in production.

## Production vs staging

| | Default gateway (production) | Staging gateway |
|---|---|---|
| URL | `https://provenance-gateway.datafund.io` (the CLI's default) | `https://provenance-gateway.dev.datafund.io` |
| Network | Base mainnet (`X402_NETWORK=base`) | Base Sepolia (`X402_NETWORK=base-sepolia`, the default) |
| Money | **Real USDC**, `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | Test USDC from the faucet, `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Use it for | Paying for real use | Integration testing only. It stores on the real Swarm network |

On both, the facilitator submits the transfer and pays the gas: the wallet needs USDC but no ETH.

The default gateway also has a free tier: `--free`, 3 requests per minute, no wallet needed.

The CLI's default network stays `base-sepolia`, so nothing is paid by accident: against the default gateway, `--x402` stops with "No payment options for network 'base-sepolia'. Available: ['base']" and the message says how to go on.

**To test** without real money, use the staging gateway with the default network:

```bash
swarm-prov-upload --gateway-url https://provenance-gateway.dev.datafund.io --x402 upload --file data.txt
```

**To pay on the default gateway**, switch the network to `base`, keep a small cap, and leave auto-pay off until you have checked the payment prompt:

```bash
X402_NETWORK=base swarm-prov-upload --x402 --max-pay 0.05 upload --file data.txt
```

The software is alpha: spend small amounts, and do not expect refunds.

## Troubleshooting

### "x402 dependencies not installed"

Install the x402 extras:
```bash
pip install -e .[x402]
```

### "No private key configured"

Set the `X402_PRIVATE_KEY` environment variable for the command, as described in [Private key](#private-key):
```bash
X402_PRIVATE_KEY="$(op read 'op://<vault>/<item>/<field>')" swarm-prov-upload x402 status
```

### "Insufficient USDC balance"

Check your balance and add USDC on the network you pay on (test USDC from the faucet for the staging gateway, real USDC for the default gateway):
```bash
swarm-prov-upload x402 balance
```

### "Payment rejected"

The signed payment may have expired or been invalid. Try the request again.

### "The payment may have been taken"

The paid request timed out, dropped, or failed with a server error after the payment was sent. The gateway collects the payment before doing the work and finishes it even if the CLI stops waiting, so the payment may have been collected and the request may even have succeeded.

**Do not re-run straight away**: a re-run signs a new payment and can pay twice. The error prints the amount, payer, pay-to address, authorization nonce and the time until which the authorization can be collected ("Valid until", about 5 minutes after signing), plus a block-explorer link for the payer. Check for a USDC transfer from the payer to the pay-to address:
- If none has appeared by the "Valid until" time, none ever will, and re-running is safe. Before then, the gateway may still be collecting it.
- If one did, and the command bought a stamp, look for the stamp among your wallet's stamps before buying another. Otherwise contact the gateway operator with the transaction.

Pressing Ctrl-C while a paid request is in progress is reported the same way, because the gateway finishes the request regardless.

A server error that the gateway sends before it collects the payment is shown as an ordinary error instead, because nothing was charged: `PURCHASE_CAPACITY`, `GATEWAY_DAILY_SPEND_CEILING`, `SPEND_BUDGET_UNAVAILABLE`, `POOL_ALLOWANCE_UNAVAILABLE`, a Bee node that has not reported a stamp price yet, a price that the gateway could not calculate, and a payment that the gateway could not verify with the facilitator. A failed settlement (`PAYMENT_SETTLEMENT_UNAVAILABLE`) is still reported as possibly charged. So are the gateway's generic server errors, such as "Could not purchase stamp. The Bee node may be unavailable.": the gateway sends the same text before and after it collects the payment. A current gateway marks the second case with `X-Payment-Status: settled_not_delivered`, but nothing in the answer shows that the gateway adds this header, or that no proxy removed it, so the CLI cannot tell the two cases apart.

### "Payment was taken, but ... failed"

The gateway confirmed it collected the payment, but the request failed afterwards. Contact the gateway operator with the transaction hash shown; they can deliver the result or refund it. Re-running pays again.

### "... most likely succeeded, but its result could not be read"

The gateway answered success, but the CLI could not read the answer (for example, a proxy page or a missing batch ID or Swarm reference). The gateway answers success only after it has collected the payment and done the work, so the request most likely worked. The CLI prints this as a warning, but still exits with code 1. Check before you contact the gateway operator: for `stamps extend`, the message shows `swarm-prov-upload stamps info <id>`, and the extension worked if the Amount it shows is higher and the TTL is longer than before the extension (with `--amount`, the message names the amount it should have grown by). The new values may take a few minutes to show.

For a stamp purchase or a stamp from the pool, the message shows `swarm-prov-upload stamps list --wallet <payer> --full`. The new stamp may show `Usable: No`, or not be listed yet, for a few minutes after the purchase. After a stamp purchase, the message also shows how the new stamp's label starts. The gateway adds a random suffix to the label of a paid purchase. The CLI sends no label, so stamps the CLI buys have a label that starts with `paid-` (most stamps from the pool start with `pool-`). The new one has 0% utilization. Only a library call of `purchase_stamp(label=...)` gives a label that starts with `<label>-`.

For an upload, or a stamp purchase whose payer is not known, there is no command to check with, and the message names what is missing (the Swarm reference or the batch ID). When the request had an Idempotency-Key, the message also shows the command that re-runs it with the same key: a gateway that supports Idempotency-Key answers that re-run from the first request (for 24 hours), without charging again, so it returns the first answer again. That gives the missing result when a proxy or the connection broke the answer; if the gateway's own answer lacked it, the replay lacks it too, but the re-run is still free. Otherwise, ask the gateway operator for it with the transaction hash shown. A re-run without the key pays again.

### "Payment received, but the stamp purchase is not confirmed yet"

The payment settled, but the Swarm node did not confirm the stamp in time. The gateway keeps waiting and registers the stamp to your wallet once the node reports it. Do not buy another one: the message shows the stamp label and the command that lists your wallet's stamps (`swarm-prov-upload stamps list --wallet <payer> --full`), where it appears under that label.

### An upload failed after the stamp was bought

The full stamp ID is printed when the stamp is bought, and again if the command then fails. Re-run the same command with `--stamp-id <id>` to use that stamp instead of buying another.

### "Refused the gateway's payment request; nothing was signed"

Before signing, the CLI checks the gateway's payment request and refuses an option that:
- uses a scheme other than `exact`;
- names a token (`asset`) other than USDC on the configured network;
- has a malformed amount or recipient; or
- pays someone other than `X402_EXPECTED_PAY_TO`, when that is set.

The message lists the reasons. A gateway that triggers this is misconfigured or not the one you meant to use.

### "x402 payments over plain http"

The gateway URL is `http://` on a host other than this machine. Anyone on the network path could rewrite the payment request, including the amount and the recipient. Use the gateway's `https://` URL.

### "Gateway advertises EIP-712 name ..."

The gateway's payment request names a different USDC signing domain than the token contract uses, so the payment would be rejected. Nothing was signed. The gateway's x402 configuration needs updating (on Base mainnet the USDC contract's name is `USD Coin`; on Base Sepolia it is `USDC`).

### "No matching network option"

The gateway doesn't support your configured network. Check that `X402_NETWORK` matches what the gateway accepts. The client treats the x402 v1 names and their CAIP-2 chain ids as the same network: `base-sepolia` is `eip155:84532` and `base` is `eip155:8453`.

The common case is the default `base-sepolia` against the default gateway, which takes only `base` (real USDC). The message then says how to go on: set `X402_NETWORK=base` (or `--x402-network base`) with a small `--max-pay` to pay real USDC, or use `--gateway-url https://provenance-gateway.dev.datafund.io` to test with test USDC, or `--free`. See [Production vs staging](#production-vs-staging).

## Security best practices

1. **Never commit private keys** to version control
2. **Use a dedicated wallet** for x402 payments, not your main wallet
3. **Start on the staging gateway or the free tier** before paying real USDC on the default gateway
4. **Set reasonable auto-pay limits** to prevent unexpected charges
5. **Review payment prompts** before confirming
6. **Keep the key out of your shell history and plaintext files**: read it from a password manager for each command; if you use a `.env` file, `chmod 600` it and never commit it

## Network details

### Base Sepolia (testnet)

| Property | Value |
|----------|-------|
| Chain ID | 84532 |
| RPC URL | https://sepolia.base.org |
| USDC Contract | 0x036CbD53842c5426634e7929541eC2318f3dCF7e |
| Block Explorer | https://sepolia.basescan.org |

### Base (mainnet)

| Property | Value |
|----------|-------|
| Chain ID | 8453 |
| RPC URL | https://mainnet.base.org |
| USDC Contract | 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 |
| Block Explorer | https://basescan.org |

## Additional resources

- [x402 Protocol Documentation](https://x402.org)
- [Base Documentation](https://docs.base.org)
- [Circle USDC Faucet](https://faucet.circle.com/)
- [EIP-712 Specification](https://eips.ethereum.org/EIPS/eip-712)
