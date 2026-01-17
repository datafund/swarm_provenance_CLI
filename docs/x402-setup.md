# x402 Payment Setup Guide

This guide walks you through setting up x402 payments for the Swarm Provenance CLI.

## What is x402?

x402 is a payment protocol that uses HTTP 402 "Payment Required" responses to enable pay-per-request APIs. When the gateway requires payment for an operation, it returns a 402 response with payment options. The CLI signs a USDC payment using your wallet and retries the request.

**Key features:**
- Pay-per-request model (no subscriptions)
- USDC stablecoin on Base chain
- EIP-712 signed messages (no gas required for signing)
- Testnet support for development

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
SWARM_X402_PRIVATE_KEY=0x...your_private_key_here...

# Network: base-sepolia (testnet) or base (mainnet)
X402_NETWORK=base-sepolia

# Optional: Auto-pay without prompts
X402_AUTO_PAY=false

# Optional: Maximum auto-pay amount per request in USD
X402_MAX_AUTO_PAY_USD=1.00
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
Payment required: $0.05 for stamp purchase
Confirm payment? [y/N]: y
Processing payment...
Upload successful: abc123...
```

### Auto-pay mode

Skip prompts for payments under your configured limit:

```bash
# Enable auto-pay for this command
swarm-prov-upload --x402 --auto-pay --max-pay 1.00 upload --file data.txt

# Or set in environment
export X402_AUTO_PAY=true
export X402_MAX_AUTO_PAY_USD=1.00
```

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

Set the `SWARM_X402_PRIVATE_KEY` environment variable:
```bash
export SWARM_X402_PRIVATE_KEY=0x...
```

### "Insufficient USDC balance"

Check your balance and get more testnet USDC:
```bash
swarm-prov-upload x402 balance
```

### "Payment rejected"

The signed payment may have expired or been invalid. Try the request again.

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
