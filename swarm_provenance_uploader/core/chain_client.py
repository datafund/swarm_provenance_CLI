"""
High-level client for on-chain provenance operations.

Provides a facade over ChainProvider, ChainWallet, and DataProvenanceContract
that mirrors the gateway_client.py pattern: simple method calls that handle
gas estimation, signing, broadcasting, and receipt parsing.

Requires optional dependencies: pip install swarm-provenance-uploader[blockchain]
"""

import os
from typing import List, Optional

from ..chain.contract import DataStatus
from ..exceptions import (
    ChainConfigurationError,
    ChainConnectionError,
    ChainTransactionError,
    ChainValidationError,
    DataNotRegisteredError,
)
from ..models import (
    AccessResult,
    AnchorResult,
    ChainProvenanceRecord,
    ChainTransformation,
    ChainWalletInfo,
    DataStatusEnum,
    TransformResult,
)


class ChainClient:
    """High-level client for DataProvenance smart contract operations.

    Wraps provider, wallet, and contract into a single interface for
    anchoring Swarm hashes on-chain, recording transformations and access,
    and querying provenance records.
    """

    def __init__(
        self,
        chain: str = "base-sepolia",
        rpc_url: Optional[str] = None,
        contract_address: Optional[str] = None,
        private_key: Optional[str] = None,
        private_key_env: str = "PROVENANCE_WALLET_KEY",
        gas_limit_multiplier: float = 1.2,
        explorer_url: Optional[str] = None,
    ):
        """
        Initialize the chain client.

        Args:
            chain: Chain name ('base-sepolia' or 'base').
            rpc_url: Custom RPC URL. If None, uses preset.
            contract_address: Custom contract address. If None, uses preset.
            private_key: Wallet private key. If None, reads from env var.
            private_key_env: Environment variable name for private key.
            gas_limit_multiplier: Safety multiplier for gas estimates (default 1.2).
            explorer_url: Custom block explorer URL. If None, uses preset.

        Raises:
            ChainConfigurationError: If dependencies missing or config invalid.
        """
        from ..chain.provider import ChainProvider
        from ..chain.wallet import ChainWallet
        from ..chain.contract import DataProvenanceContract

        self._provider = ChainProvider(
            chain=chain,
            rpc_url=rpc_url,
            contract_address=contract_address,
            explorer_url=explorer_url,
        )
        self._wallet = ChainWallet(
            private_key=private_key,
            private_key_env=private_key_env,
        )
        self._contract = DataProvenanceContract(
            web3=self._provider.web3,
            contract_address=self._provider.contract_address,
        )
        self._gas_limit_multiplier = gas_limit_multiplier

    @property
    def address(self) -> str:
        """Wallet address."""
        return self._wallet.address

    @property
    def chain(self) -> str:
        """Chain name."""
        return self._provider.chain

    @property
    def contract_address(self) -> str:
        """DataProvenance contract address."""
        return self._provider.contract_address

    # --- Internal helpers ---

    def _send_transaction(self, tx: dict, verbose: bool = False) -> dict:
        """
        Estimate gas, sign, broadcast, and wait for receipt.

        Args:
            tx: Unsigned transaction dict from a build_*_tx method.
            verbose: Enable debug output.

        Returns:
            Transaction receipt dict.

        Raises:
            ChainTransactionError: If transaction fails.
        """
        web3 = self._provider.web3

        try:
            # Fill in nonce
            tx["nonce"] = web3.eth.get_transaction_count(self._wallet.address)
            tx["chainId"] = self._provider.chain_id

            # Estimate gas with safety multiplier
            estimated_gas = web3.eth.estimate_gas(tx)
            tx["gas"] = int(estimated_gas * self._gas_limit_multiplier)

            if verbose:
                print(f"DEBUG: Estimated gas: {estimated_gas}, limit: {tx['gas']}")

            # Sign and send
            raw_tx = self._wallet.sign_transaction(tx)
            tx_hash = web3.eth.send_raw_transaction(raw_tx)

            if verbose:
                print(f"DEBUG: Transaction sent: {tx_hash.hex()}")

            # Wait for receipt
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt["status"] != 1:
                raise ChainTransactionError(
                    f"Transaction reverted (status=0)",
                    tx_hash=tx_hash.hex(),
                )

            if verbose:
                print(f"DEBUG: Transaction confirmed in block {receipt['blockNumber']}")
                print(f"DEBUG: Gas used: {receipt['gasUsed']}")

            return receipt

        except ChainTransactionError:
            raise
        except Exception as e:
            tx_hash_str = None
            if "tx_hash" in dir():
                tx_hash_str = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
            raise ChainTransactionError(
                f"Transaction failed: {e}",
                tx_hash=tx_hash_str,
            ) from e

    def _receipt_to_explorer_url(self, receipt: dict) -> Optional[str]:
        """Get explorer URL from a transaction receipt."""
        tx_hash = receipt.get("transactionHash")
        if tx_hash:
            return self._provider.get_explorer_tx_url(tx_hash.hex())
        return None

    # --- Write operations ---

    def anchor(
        self,
        swarm_hash: str,
        data_type: str = "swarm-provenance",
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Anchor a Swarm hash on-chain by registering it in the DataProvenance contract.

        Args:
            swarm_hash: Swarm reference hash (64 hex chars).
            data_type: Data type/category (max 64 chars, default 'swarm-provenance').
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        if verbose:
            print(f"--- DEBUG: Anchor ---")
            print(f"Hash: {swarm_hash}")
            print(f"Type: {data_type}")

        tx = self._contract.build_register_data_tx(
            data_hash=swarm_hash,
            data_type=data_type,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type=data_type,
            owner=self._wallet.address,
        )

    def anchor_for(
        self,
        swarm_hash: str,
        owner: str,
        data_type: str = "swarm-provenance",
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Anchor a Swarm hash on behalf of another owner.

        Caller must be an authorized delegate of the owner.

        Args:
            swarm_hash: Swarm reference hash.
            owner: Address of the actual data owner.
            data_type: Data type/category.
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        if verbose:
            print(f"--- DEBUG: Anchor For ---")
            print(f"Hash: {swarm_hash}")
            print(f"Owner: {owner}")

        tx = self._contract.build_register_data_for_tx(
            data_hash=swarm_hash,
            data_type=data_type,
            actual_owner=owner,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type=data_type,
            owner=owner,
        )

    def batch_anchor(
        self,
        swarm_hashes: List[str],
        data_types: List[str],
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Anchor multiple Swarm hashes in a single transaction.

        Args:
            swarm_hashes: List of Swarm reference hashes.
            data_types: List of data type strings (same length).
            verbose: Enable debug output.

        Returns:
            AnchorResult for the batch transaction (swarm_hash is first hash).
        """
        if verbose:
            print(f"--- DEBUG: Batch Anchor ---")
            print(f"Count: {len(swarm_hashes)}")

        tx = self._contract.build_batch_register_data_tx(
            data_hashes=swarm_hashes,
            data_types=data_types,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hashes[0] if swarm_hashes else "",
            data_type=data_types[0] if data_types else "",
            owner=self._wallet.address,
        )

    def transform(
        self,
        original_hash: str,
        new_hash: str,
        description: str,
        verbose: bool = False,
    ) -> TransformResult:
        """
        Record a data transformation on-chain.

        Args:
            original_hash: Hash of the original data.
            new_hash: Hash of the transformed data.
            description: Transformation description (max 256 chars).
            verbose: Enable debug output.

        Returns:
            TransformResult with transaction details.
        """
        if verbose:
            print(f"--- DEBUG: Transform ---")
            print(f"Original: {original_hash}")
            print(f"New: {new_hash}")
            print(f"Description: {description}")

        tx = self._contract.build_record_transformation_tx(
            original_hash=original_hash,
            new_hash=new_hash,
            description=description,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return TransformResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            original_hash=original_hash,
            new_hash=new_hash,
            description=description,
        )

    def access(
        self,
        swarm_hash: str,
        verbose: bool = False,
    ) -> AccessResult:
        """
        Record that data was accessed.

        Args:
            swarm_hash: Hash of the accessed data.
            verbose: Enable debug output.

        Returns:
            AccessResult with transaction details.
        """
        if verbose:
            print(f"--- DEBUG: Record Access ---")
            print(f"Hash: {swarm_hash}")

        tx = self._contract.build_record_access_tx(
            data_hash=swarm_hash,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AccessResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            accessor=self._wallet.address,
        )

    def batch_access(
        self,
        swarm_hashes: List[str],
        verbose: bool = False,
    ) -> AccessResult:
        """
        Record access to multiple data hashes in a single transaction.

        Args:
            swarm_hashes: List of accessed data hashes.
            verbose: Enable debug output.

        Returns:
            AccessResult for the batch transaction.
        """
        if verbose:
            print(f"--- DEBUG: Batch Access ---")
            print(f"Count: {len(swarm_hashes)}")

        tx = self._contract.build_batch_record_access_tx(
            data_hashes=swarm_hashes,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AccessResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hashes[0] if swarm_hashes else "",
            accessor=self._wallet.address,
        )

    def set_status(
        self,
        swarm_hash: str,
        status: int,
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Set the status of a registered data hash.

        Args:
            swarm_hash: Hash of the data.
            status: New status (0=ACTIVE, 1=RESTRICTED, 2=DELETED).
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        if verbose:
            print(f"--- DEBUG: Set Status ---")
            print(f"Hash: {swarm_hash}")
            print(f"Status: {DataStatus(status).name}")

        tx = self._contract.build_set_data_status_tx(
            data_hash=swarm_hash,
            status=status,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type="",
            owner=self._wallet.address,
        )

    def batch_set_status(
        self,
        swarm_hashes: List[str],
        statuses: List[int],
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Set the status of multiple registered data hashes in a single transaction.

        Args:
            swarm_hashes: List of data hashes.
            statuses: List of new statuses (0=ACTIVE, 1=RESTRICTED, 2=DELETED).
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        if verbose:
            print(f"--- DEBUG: Batch Set Status ---")
            print(f"Count: {len(swarm_hashes)}")

        tx = self._contract.build_batch_set_data_status_tx(
            data_hashes=swarm_hashes,
            statuses=statuses,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hashes[0] if swarm_hashes else "",
            data_type="",
            owner=self._wallet.address,
        )

    def transfer_ownership(
        self,
        swarm_hash: str,
        new_owner: str,
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Transfer ownership of a data hash to a new address.

        Args:
            swarm_hash: Hash of the data.
            new_owner: Address of the new owner.
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        if verbose:
            print(f"--- DEBUG: Transfer Ownership ---")
            print(f"Hash: {swarm_hash}")
            print(f"New owner: {new_owner}")

        tx = self._contract.build_transfer_ownership_tx(
            data_hash=swarm_hash,
            new_owner=new_owner,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type="",
            owner=new_owner,
        )

    def set_delegate(
        self,
        delegate: str,
        authorized: bool = True,
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Authorize or revoke a delegate address.

        Args:
            delegate: Address to authorize/revoke.
            authorized: True to authorize, False to revoke.
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        if verbose:
            action = "Authorize" if authorized else "Revoke"
            print(f"--- DEBUG: {action} Delegate ---")
            print(f"Delegate: {delegate}")

        tx = self._contract.build_set_delegate_tx(
            delegate=delegate,
            authorized=authorized,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash="",
            data_type="",
            owner=self._wallet.address,
        )

    # --- Read operations ---

    def get(
        self,
        swarm_hash: str,
        verbose: bool = False,
    ) -> ChainProvenanceRecord:
        """
        Get the on-chain provenance record for a Swarm hash.

        Args:
            swarm_hash: Swarm reference hash.
            verbose: Enable debug output.

        Returns:
            ChainProvenanceRecord with full provenance data.

        Raises:
            DataNotRegisteredError: If hash is not registered on-chain.
        """
        if verbose:
            print(f"--- DEBUG: Get Record ---")
            print(f"Hash: {swarm_hash}")

        record = self._contract.get_data_record(swarm_hash)

        # record is a tuple: (dataHash, owner, timestamp, dataType,
        #                      transformations, accessors, status)
        data_hash_bytes, owner, timestamp, data_type, transformations, accessors, status = record

        # Check if data is registered (owner is zero address if not)
        zero_address = "0x" + "0" * 40
        if owner == zero_address:
            raise DataNotRegisteredError(
                f"Data hash {swarm_hash} is not registered on-chain",
                data_hash=swarm_hash,
            )

        # Parse transformations — contract returns string[] (description only)
        chain_transformations = []
        for t in transformations:
            chain_transformations.append(ChainTransformation(
                description=str(t),
            ))

        if verbose:
            print(f"DEBUG: Owner: {owner}")
            print(f"DEBUG: Type: {data_type}")
            print(f"DEBUG: Status: {DataStatus(status).name}")
            print(f"DEBUG: Accessors: {len(accessors)}")

        return ChainProvenanceRecord(
            data_hash=data_hash_bytes.hex() if isinstance(data_hash_bytes, bytes) else str(data_hash_bytes),
            owner=owner,
            timestamp=timestamp,
            data_type=data_type,
            status=DataStatusEnum(status),
            accessors=list(accessors),
            transformations=chain_transformations,
        )

    def verify(
        self,
        swarm_hash: str,
        verbose: bool = False,
    ) -> bool:
        """
        Verify that a Swarm hash is registered on-chain.

        Args:
            swarm_hash: Swarm reference hash.
            verbose: Enable debug output.

        Returns:
            True if registered, False if not.
        """
        try:
            self.get(swarm_hash, verbose=verbose)
            return True
        except DataNotRegisteredError:
            return False

    def balance(self, verbose: bool = False) -> ChainWalletInfo:
        """
        Get wallet balance and chain info.

        Args:
            verbose: Enable debug output.

        Returns:
            ChainWalletInfo with balance and chain details.
        """
        if verbose:
            print(f"--- DEBUG: Balance ---")

        balance_wei = self._wallet.get_balance(self._provider.web3)
        balance_eth = self._wallet.get_balance_eth(self._provider.web3)

        if verbose:
            print(f"DEBUG: Address: {self._wallet.address}")
            print(f"DEBUG: Balance: {balance_eth} ETH")

        return ChainWalletInfo(
            address=self._wallet.address,
            balance_wei=balance_wei,
            balance_eth=balance_eth,
            chain=self._provider.chain,
            contract_address=self._provider.contract_address,
        )

    def health_check(self, verbose: bool = False) -> bool:
        """
        Check if the chain provider is connected and healthy.

        Args:
            verbose: Enable debug output.

        Returns:
            True if healthy.

        Raises:
            ChainConnectionError: If health check fails.
        """
        if verbose:
            print(f"--- DEBUG: Chain Health Check ---")
            print(f"Chain: {self._provider.chain}")
            print(f"RPC: {self._provider.rpc_url}")

        result = self._provider.health_check()

        if verbose:
            block = self._provider.get_block_number()
            print(f"DEBUG: Connected, block: {block}")

        return result

    def get_provenance_chain(
        self,
        swarm_hash: str,
        max_depth: Optional[int] = None,
        verbose: bool = False,
    ) -> List[ChainProvenanceRecord]:
        """
        Get the provenance chain for a data hash.

        Retrieves the record for the given hash. If transformations have
        new_data_hash links, follows them to build a lineage chain.

        Note: The current contract returns transformation descriptions only
        (no new_data_hash links), so the chain will typically contain just
        the queried record. Supply hashes directly to follow known lineages.

        Args:
            swarm_hash: Starting Swarm reference hash.
            max_depth: Maximum traversal depth. None means no limit (capped at 50).
            verbose: Enable debug output.

        Returns:
            List of ChainProvenanceRecord forming the provenance chain,
            starting with the given hash.
        """
        if verbose:
            print(f"--- DEBUG: Get Provenance Chain ---")
            print(f"Starting hash: {swarm_hash}")
            if max_depth is not None:
                print(f"Max depth: {max_depth}")

        effective_max = max_depth if max_depth is not None else 50

        chain = []
        visited = set()
        to_visit = [(swarm_hash, 0)]

        while to_visit:
            current_hash, current_depth = to_visit.pop(0)
            if current_hash in visited:
                continue
            if current_depth > effective_max:
                if verbose:
                    print(f"DEBUG: Depth limit reached at {current_depth}")
                continue
            visited.add(current_hash)

            try:
                record = self.get(current_hash, verbose=verbose)
                chain.append(record)

                # Follow transformation links if new_data_hash is available
                for t in record.transformations:
                    if t.new_data_hash and t.new_data_hash not in visited:
                        to_visit.append((t.new_data_hash, current_depth + 1))
            except DataNotRegisteredError:
                if verbose:
                    print(f"DEBUG: Hash {current_hash} not registered, skipping")
                continue

        if verbose:
            print(f"DEBUG: Chain length: {len(chain)}")

        return chain
