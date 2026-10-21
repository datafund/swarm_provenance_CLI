# x402 Payment Setup Guide

This guide walks you through setting up x402 payments for the Swarm Provenance CLI.

## What is x402?

x402 is a payment protocol that uses HTTP 402 "Payment Required" responses to enable pay-per-request APIs. When the gateway requires payment for an operation, it returns a 402 response with payment options. The CLI signs a USDC payment using your wallet and retries the request.

**Key features:**
- Pay-per-request model (no subscriptions)
- USDC stablecoin on Base chain
- EIP-712 signed messages (no gas required for signing)
- Testnet support for development

### How It Works

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

- Python 3.8+
- An Ethereum wallet (MetaMask, hardware wallet, etc.)
- Base Sepolia ETH (for gas, testnet only)
- Base Sepolia USDC (for payments, testnet only)

## Step 1: Install x402 Dependencies

Install the CLI with x402 support:

```bash
pip install -e .[x402]
```

This installs:
- `eth-account` - Ethereum account management and signing
- `web3` - Blockchain interaction
- `x402` - x402 protocol library

## Step 2: Create or Export a Wallet

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

## Step 3: Get Testnet Funds

For development and testing, use Base Sepolia testnet.

### Get testnet ETH (for gas)

1. Go to https://www.alchemy.com/faucets/base-sepolia
2. Enter your wallet address
3. Request test ETH

Alternative faucets:
- https://faucet.quicknode.com/base/sepolia
- https://www.coinbase.com/faucets/base-ethereum-goerli-faucet

### Get testnet USDC (for payments)

1. Go to https://faucet.circle.com/
2. Select "Base Sepolia" network
3. Enter your wallet address
4. Request test USDC

The USDC contract on Base Sepolia is: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`

## Step 4: Configure the CLI

### Environment variables

Add to your `.env` file:

```bash
# Enable x402 payments
X402_ENABLED=true

# Your wallet private key (KEEP SECRET!)
X402_PRIVATE_KEY=0x...your_private_key_here...

# Network: base-sepolia (testnet) or base (mainnet)
X402_NETWORK=base-sepolia

# Optional: Auto-pay without prompts
X402_AUTO_PAY=false

# Optional: Maximum auto-pay amount per request in USD
X402_MAX_AUTO_PAY_USD=1.00

# Optional: Only pay this recipient (the gateway operator's published pay-to address)
X402_EXPECTED_PAY_TO=0x...
```

### Verify configuration

```bash
# Check x402 status
swarm-prov-upload x402 status

# Check your USDC balance
swarm-prov-upload x402 balance
```

## Step 5: Make a Payment

### Interactive mode (default)

When x402 is enabled and a request requires payment, you'll see a confirmation prompt:

```bash
swarm-prov-upload --x402 upload --file data.txt
```

Output:
```
Payment required: $0.050000 USDC
  For:     Stamp purchase
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

## Switching to Mainnet

When ready for production:

1. Get real USDC on Base mainnet
2. Update your `.env`:

```bash
X402_NETWORK=base
```

**Warning:** Mainnet uses real funds. Start with small amounts and test thoroughly.

## Troubleshooting

### "x402 dependencies not installed"

Install the x402 extras:
```bash
pip install -e .[x402]
```

### "No private key configured"

Set the `X402_PRIVATE_KEY` environment variable:
```bash
export X402_PRIVATE_KEY=0x...
```

### "Insufficient USDC balance"

Check your balance and get more testnet USDC:
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

### "Payment was taken, but ... failed"

The gateway confirmed it collected the payment, but the request failed afterwards (or it answered success with a response the CLI could not read). Contact the gateway operator with the transaction hash shown; they can deliver the result or refund it. Re-running pays again.

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

The gateway doesn't support your configured network. Check that `X402_NETWORK` matches what the gateway accepts.

## Security Best Practices

1. **Never commit private keys** to version control
2. **Use a dedicated wallet** for x402 payments, not your main wallet
3. **Start with testnet** before using real funds
4. **Set reasonable auto-pay limits** to prevent unexpected charges
5. **Review payment prompts** before confirming
6. **Use environment files** (`.env`) instead of command line arguments for secrets

## Network Details

### Base Sepolia (Testnet)

| Property | Value |
|----------|-------|
| Chain ID | 84532 |
| RPC URL | https://sepolia.base.org |
| USDC Contract | 0x036CbD53842c5426634e7929541eC2318f3dCF7e |
| Block Explorer | https://sepolia.basescan.org |

### Base (Mainnet)

| Property | Value |
|----------|-------|
| Chain ID | 8453 |
| RPC URL | https://mainnet.base.org |
| USDC Contract | 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 |
| Block Explorer | https://basescan.org |

## Additional Resources

- [x402 Protocol Documentation](https://x402.org)
- [Base Documentation](https://docs.base.org)
- [Circle USDC Faucet](https://faucet.circle.com/)
- [EIP-712 Specification](https://eips.ethereum.org/EIPS/eip-712)
