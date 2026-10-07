"""Optional dependency requirements, in one place for the install hints.

They must match the `x402` and `blockchain` extras in pyproject.toml (a test
checks this). The floors are what the code needs: `sign_typed_data` exists
from eth-account 0.13.5, `raw_transaction` from 0.13.0, and web3 7 is the
first line that accepts those eth-account versions.
"""

WEB3_REQUIREMENT = "web3>=7.0.0"
ETH_ACCOUNT_REQUIREMENT = "eth-account>=0.13.5"

#: Shell command that installs the signing dependencies (x402 and chain)
INSTALL_SIGNING_DEPS = f'pip install "{WEB3_REQUIREMENT}" "{ETH_ACCOUNT_REQUIREMENT}"'
#: Shell command that installs eth-account alone (notary verification)
INSTALL_ETH_ACCOUNT = f'pip install "{ETH_ACCOUNT_REQUIREMENT}"'
