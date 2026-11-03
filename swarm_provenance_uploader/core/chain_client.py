"""
High-level client for on-chain provenance operations.

Provides a facade over ChainProvider, ChainWallet, and DataProvenanceContract
that mirrors the gateway_client.py pattern: simple method calls that handle
gas estimation, signing, broadcasting, and receipt parsing.

Requires optional dependencies (the `blockchain` extra): web3 and eth-account.
"""

import ast
import functools
import json
import logging
from typing import List, Optional

from ..chain.contract import DataStatus
from ..chain.redact import redact_url, redact_urls
from ..chain.exceptions import (
    ChainError,
    ChainConfigurationError,
    ChainConnectionError,
    ChainTransactionError,
    ChainValidationError,
    InsufficientFundsError,
    TransactionNotRecordedError,
    TransactionNotVerifiedError,
    TransactionOutcomeUnknownError,
    ReceiptTimeoutError,
    TransactionReplacedError,
    TransactionNotFoundError,
    DataAlreadyRegisteredError,
    DataNotRegisteredError,
    TransformationAlreadyExistsError,
)
from ..models import (
    AccessResult,
    AnchorResult,
    ChainProvenanceRecord,
    ChainTransformation,
    ChainWalletInfo,
    DataStatusEnum,
    MergeTransformResult,
    TransformResult,
    TransactionWaitResult,
)
from ..chain.exceptions import redact_exception_chain, replaced_check_advice

logger = logging.getLogger(__name__)

# Balance thresholds for pre-flight checks
MIN_BALANCE_WEI = 100_000_000_000_000       # 0.0001 ETH — hard floor
LOW_BALANCE_WEI = 1_000_000_000_000_000     # 0.001 ETH  — warning threshold


def _is_rpc_failure(error: Exception) -> bool:
    """True if an error comes from reaching the RPC, not from bad input."""
    if isinstance(error, OSError):  # includes requests' connection errors and timeouts
        return True
    if isinstance(error, json.JSONDecodeError):
        # The endpoint answered, but not with JSON-RPC (an HTML or proxy error page)
        return True
    try:
        from web3 import exceptions as web3_exceptions
    except ImportError:
        return False
    rpc_errors = tuple(
        cls
        for cls in (
            getattr(web3_exceptions, "Web3RPCError", None),
            getattr(web3_exceptions, "ProviderConnectionError", None),
            getattr(web3_exceptions, "TimeExhausted", None),
            getattr(web3_exceptions, "BadResponseFormat", None),
        )
        if isinstance(cls, type)
    )
    return bool(rpc_errors) and isinstance(error, rpc_errors)



def _is_contract_revert(error: Exception) -> bool:
    """True if web3 reports that the contract reverted (ContractLogicError).

    Matched by class name, so it also covers ContractCustomError and
    ContractPanicError without importing web3.
    """
    return any(cls.__name__ == "ContractLogicError" for cls in type(error).__mro__)


def _is_rpc_rejection(error: Exception) -> bool:
    """True if the node answered with a JSON-RPC error (web3 Web3RPCError).

    The connection worked; the node refused the request, for example
    "nonce too low". Matched by class name, like _is_contract_revert.
    RequestTimedOut subclasses Web3RPCError but is a timeout, not a refusal.
    """
    names = {cls.__name__ for cls in type(error).__mro__}
    return "Web3RPCError" in names and "RequestTimedOut" not in names


def _is_receipt_timeout(error: Exception) -> bool:
    """True if web3's receipt wait timed out (TimeExhausted).

    Matched by class name, like _is_contract_revert. _is_rpc_failure counts
    it as an RPC failure; _send_transaction leaves it to its own handling.
    """
    return any(cls.__name__ == "TimeExhausted" for cls in type(error).__mro__)


def _is_transaction_not_found(error: Exception) -> bool:
    """True if web3 reports that the RPC does not know a transaction (TransactionNotFound).

    Matched by class name, like _is_contract_revert.
    """
    return any(cls.__name__ == "TransactionNotFound" for cls in type(error).__mro__)


# How long a write waits for its receipt, in seconds (also the chain wait default)
RECEIPT_TIMEOUT = 120


def _is_transport_failure(error: Exception) -> bool:
    """True if another RPC endpoint may succeed where this one failed (#168).

    A ChainConnectionError, or an RPC failure (_is_rpc_failure) that is not
    a JSON-RPC error answer and not a receipt-wait timeout. A node that
    answered with a JSON-RPC error, a contract revert, or a node on the
    wrong chain (ChainIdMismatchError) is not one: another endpoint would
    give the same answer, or must not be used.
    """
    if isinstance(error, ChainConnectionError):
        return True
    return (
        _is_rpc_failure(error)
        and not _is_rpc_rejection(error)
        and not _is_receipt_timeout(error)
    )


def _with_fallback(provider, operation):
    """
    Run operation, and run it again on a fallback RPC after a transport failure (#168).

    On a transport failure (_is_transport_failure), the provider switches
    to the next fallback endpoint that connects and reports the chain ID in
    use (ChainProvider._try_fallback), and operation runs again. Each
    endpoint is tried at most once per call. When no endpoint is left, the
    last error is raised, for the caller to map.

    Only operations that can safely run twice go through here: reads, and
    the steps of a write before send_raw_transaction. A send is never run
    again.

    Only the outermost call runs the loop. A call made while a loop is
    already active (a read such as verify() calling get()) runs operation
    once and leaves the fallback to the outer loop. ChainProvider's
    health_check() and get_block_number() do the same with their own loops.
    The steps of one public call share one set of tried endpoints
    (``provider._fallback_tried``, set by _redacted_errors), so a later step
    does not go back to an endpoint that an earlier step left. Together, one
    public call tries each endpoint at most once.
    """
    if getattr(provider, "_fallback_active", False) is True:
        # The outer loop handles a transport failure and runs its whole
        # operation again; running a loop here as well would also reset
        # _fallback_active in its finally while the outer loop still runs
        return operation()
    provider._fallback_active = True
    try:
        tried = getattr(provider, "_fallback_tried", None)
        if not isinstance(tried, set):
            tried = set()
        while True:
            try:
                return operation()
            except Exception as e:
                if not _is_transport_failure(e):
                    raise
                failed_url = provider.rpc_url
                tried.add(failed_url)
                if provider._try_fallback(tried) is not True:
                    raise
                logger.debug(
                    "RPC request to %s failed (%s); trying again on %s",
                    redact_url(failed_url),
                    redact_urls(_error_reason(e)),
                    redact_url(provider.rpc_url),
                )
    finally:
        provider._fallback_active = False


def _duplicate_check_connection_error(error: Exception, rpc_url: Optional[str]) -> ChainConnectionError:
    """The error for transform()'s duplicate check when no RPC endpoint is left (#168)."""
    if isinstance(error, ChainConnectionError):
        rpc_url = error.rpc_url
    return ChainConnectionError(
        f"The RPC endpoint failed during the duplicate transformation check: "
        f"{_error_reason(error)}. Nothing was sent.",
        rpc_url=rpc_url,
    )


def _signed_tx_hash(raw_tx) -> Optional[str]:
    """The hash of a signed transaction (keccak-256 of its bytes), or None.

    The same value send_raw_transaction returns, so it is known even when
    the send raised before it returned. Formatted like the returned hash,
    with HexBytes.hex(), so the format (with or without "0x") follows the
    installed hexbytes version.
    """
    try:
        from .swarm_verify import keccak256

        digest = keccak256(bytes(raw_tx))
    except Exception:
        return None
    try:
        from hexbytes import HexBytes
    except ImportError:
        return digest.hex()
    return HexBytes(digest).hex()


def _error_reason(error: Exception) -> str:
    """The readable reason of a web3 error.

    str() of a ContractLogicError is the (message, data) tuple, and a
    Web3RPCError's message is often the repr of the JSON-RPC error object,
    such as "{'code': -32000, 'message': 'nonce too low'}". Return only the
    message in both cases. Never empty: falls back to the class name.
    """
    rpc_error = (getattr(error, "rpc_response", None) or {})
    rpc_error = rpc_error.get("error") if isinstance(rpc_error, dict) else None
    if isinstance(rpc_error, dict) and rpc_error.get("message"):
        return str(rpc_error["message"])
    message = getattr(error, "message", None)
    if isinstance(message, str) and message.startswith("{") and len(message) <= 4096:
        try:
            message = ast.literal_eval(message)
        except Exception:  # SyntaxError, ValueError, TypeError, MemoryError, RecursionError
            pass
    if isinstance(message, dict) and message.get("message"):
        return str(message["message"])
    if isinstance(message, str) and message:
        return message
    # An exception with no arguments has an empty str(): name its class
    return str(error) or type(error).__name__


# Provenance chain walk depth (#170): the default, and the largest accepted
DEFAULT_CHAIN_DEPTH = 10
MAX_CHAIN_DEPTH = 50


def _traversal_error(data_hash: str, depth: int, error: Exception) -> ChainError:
    """The error that stops a provenance chain walk at one node (#170).

    The walk fails closed: a partial lineage is never returned. A JSON-RPC
    error answer becomes ChainConfigurationError, as in _read_error: the
    node answered, so it is not a connection failure and the walk does not
    move to a fallback (#168). Other RPC failures become
    ChainConnectionError and everything else ChainError; all name the node
    and its depth. Chain errors other than connection and
    not-registered errors (for example ChainValidationError) keep their
    class. A linked hash that reads as not registered means an inconsistent
    read (the contract registers every derived hash), so it is a ChainError
    and not DataNotRegisteredError, which callers read as "start hash not
    found". Messages are URL-redacted by ChainError.
    """
    if isinstance(error, ChainError) and not isinstance(
        error, (ChainConnectionError, DataNotRegisteredError)
    ):
        return error
    if isinstance(error, DataNotRegisteredError):
        reason = "the linked record reads as not registered (inconsistent read)"
    else:
        reason = _error_reason(error)
    message = f"Provenance chain read failed at {data_hash} (depth {depth}): {reason}"
    if isinstance(error, ChainConnectionError):
        return ChainConnectionError(message, rpc_url=error.rpc_url)
    if _is_rpc_rejection(error):
        # Checked before _is_rpc_failure, which also counts a JSON-RPC error answer
        return ChainConfigurationError(
            f"Provenance chain read failed at {data_hash} (depth {depth}): "
            f"The RPC rejected the request: {reason}"
        )
    if _is_rpc_failure(error):
        return ChainConnectionError(message)
    return ChainError(message)


def _traversal_cause(error: Exception) -> Optional[BaseException]:
    """The cause to chain to the error _traversal_error makes from error.

    A raw failure is the cause itself. A ChainError keeps its own cause,
    for example the RPC failure that a read method mapped (#187), so the
    traceback shows where the read failed, and a ChainError that
    _traversal_error returns unchanged is not made its own cause.
    ChainClient's public methods redact the chain (redact_exception_chain),
    so the RPC URL is not repeated through it.
    """
    if isinstance(error, ChainError):
        return error.__cause__
    return error


def _rpc_rejection_message(error: Exception) -> Optional[str]:
    """The node's message if error is a JSON-RPC error answer, else None.

    A Web3RPCError means the node answered and refused the request (for
    example "nonce too low"), so it is not a connection failure. Its
    RequestTimedOut subclass is: the node did not answer in time. The
    message is _error_reason's, so a Web3RPCError whose text is the repr of
    the JSON-RPC error object gives only the node's message. Callers redact
    it (#169).
    """
    if not _is_rpc_rejection(error):
        return None
    return _error_reason(error)


def _read_error(error: Exception, rpc_url: Optional[str]) -> Optional[ChainError]:
    """The chain error for an RPC failure in a read, or None if it is not one (#187).

    A JSON-RPC error answer becomes ChainConfigurationError, like the
    contract code check; a transport failure, a timeout or an answer that
    is not JSON-RPC becomes ChainConnectionError. ChainError redacts the
    message, and ChainConnectionError the URL.
    """
    rejection = _rpc_rejection_message(error)
    if rejection is not None:
        return ChainConfigurationError(f"The RPC rejected the request: {rejection}")
    if _is_rpc_failure(error):
        return ChainConnectionError(_error_reason(error), rpc_url=rpc_url)
    return None


def _redacted_errors(map_rpc_failures: bool):
    """Decorate a public ChainClient method so its errors do not repeat the RPC URL (#187).

    A ChainError the method raises gets a redacted exception chain
    (redact_exception_chain), because library callers can print
    ``__cause__`` and ``__context__``. With map_rpc_failures (read
    methods), the method is run again on a fallback RPC endpoint after a
    transport failure (_with_fallback, #168), and a raw RPC
    failure becomes a chain error (_read_error), raised from it, so the
    redacted original stays in ``__cause__`` and a traceback still shows
    where it failed. Other exceptions pass through unchanged.
    """
    def decorator(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            # One set of tried endpoints for the whole public call (#168):
            # the outermost decorated method creates it, nested ones reuse it
            provider = self._provider
            owns_tried = not isinstance(getattr(provider, "_fallback_tried", None), set)
            if owns_tried:
                provider._fallback_tried = set()
            try:
                try:
                    if map_rpc_failures:
                        # Reads change nothing, so running one again is safe
                        return _with_fallback(self._provider, lambda: method(self, *args, **kwargs))
                    return method(self, *args, **kwargs)
                except ChainError:
                    raise
                except Exception as e:
                    if not map_rpc_failures:
                        raise
                    error = _read_error(e, self._provider.rpc_url)
                    if error is None:
                        raise
                    raise error from e
            except ChainError as e:
                redact_exception_chain(e)
                raise
            finally:
                if owns_tried:
                    provider._fallback_tried = None
        return wrapper
    return decorator


_read_method = _redacted_errors(map_rpc_failures=True)
_write_method = _redacted_errors(map_rpc_failures=False)


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
        gas_limit: Optional[int] = None,
        rpc_fallbacks: Optional[List[str]] = None,
        require_wallet: bool = True,
    ):
        """
        Initialize the chain client.

        Args:
            chain: Chain name ('base-sepolia', 'base', or 'localhost').
            rpc_url: Custom RPC URL. If None, uses preset.
            contract_address: Custom contract address. If None, uses preset.
            private_key: Wallet private key. If None, reads from env var.
            private_key_env: Environment variable name for private key.
            gas_limit_multiplier: Safety multiplier for gas estimates (default 1.2).
            explorer_url: Custom block explorer URL. If None, uses preset.
            gas_limit: Explicit gas limit. If set, skips estimation and multiplier.
            rpc_fallbacks: Fallback RPC URLs tried in order on failure.
            require_wallet: If True (default), load the wallet key now. If
                False, load it on first use, so read-only operations work
                without a key. Writes, balance() and address then raise
                ChainConfigurationError when no key is configured.

        Raises:
            ChainConfigurationError: If dependencies missing or config invalid,
                or if require_wallet is True and no valid key is configured.
        """
        from ..chain.provider import ChainProvider
        from ..chain.contract import DataProvenanceContract

        self._provider = ChainProvider(
            chain=chain,
            rpc_url=rpc_url,
            contract_address=contract_address,
            explorer_url=explorer_url,
            rpc_fallbacks=rpc_fallbacks,
        )
        self._private_key = private_key
        self._private_key_env = private_key_env
        self._wallet_instance = None
        if require_wallet:
            self._wallet  # load the key now: fail here if it is missing
        self._contract = DataProvenanceContract(
            web3=self._provider.web3,
            contract_address=self._provider.contract_address,
        )
        self._gas_limit_multiplier = gas_limit_multiplier
        self._gas_limit = gas_limit
        self._contract_code_checked = False

    @property
    def _wallet(self):
        """The signing wallet, created on first use.

        Raises:
            ChainConfigurationError: If no valid private key is configured.
        """
        if self._wallet_instance is None:
            from ..chain.wallet import ChainWallet

            self._wallet_instance = ChainWallet(
                private_key=self._private_key,
                private_key_env=self._private_key_env,
            )
            self._private_key = None  # the wallet holds it from now on
        return self._wallet_instance

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

    def _check_balance(self, estimated_cost_wei: int = 0) -> None:
        """
        Pre-flight balance check before sending a transaction.

        Args:
            estimated_cost_wei: Estimated transaction cost in wei.

        Raises:
            InsufficientFundsError: If balance is below the estimated cost
                or below the hard minimum (MIN_BALANCE_WEI).
        """
        import sys

        balance_wei = self._wallet.get_balance(self._provider.web3)
        threshold = max(estimated_cost_wei, MIN_BALANCE_WEI)

        if balance_wei < threshold:
            balance_eth = balance_wei / 1e18
            cost_eth = estimated_cost_wei / 1e18
            raise InsufficientFundsError(
                f"Insufficient funds: balance {balance_eth:.6f} ETH, "
                f"estimated cost {cost_eth:.6f} ETH",
                wallet_address=self._wallet.address,
                balance_wei=balance_wei,
                estimated_cost_wei=estimated_cost_wei,
                chain_name=self._provider.chain,
            )

        if balance_wei < LOW_BALANCE_WEI:
            import typer
            balance_eth = balance_wei / 1e18
            typer.secho(
                f"WARNING: Low balance ({balance_eth:.6f} ETH). "
                f"Transaction may fail if gas prices spike.",
                fg=typer.colors.YELLOW,
                err=True,
            )

    def _check_contract_code(self) -> None:
        """
        Refuse to write to the wrong chain or to an address without code.

        First the RPC's chain ID is confirmed (ChainProvider.confirm_chain_id),
        then the code at the contract address is read: a transaction to an
        address without code succeeds and records nothing. Both are checked
        once per client, before the first signature.

        Raises:
            ChainIdMismatchError: If the RPC is on another chain than a named
                network preset.
            ChainConfigurationError: If the address has no contract code, the
                RPC rejected the check (a JSON-RPC error answer), or the check
                fails for a reason other than the RPC.
            ChainConnectionError: If the RPC cannot be reached.
        """
        _with_fallback(self._provider, self._provider.confirm_chain_id)
        if self._contract_code_checked:
            return
        # The checksummed address: web3 rejects a lowercase one, and the
        # event check compares against the same value.
        address = self._contract.address
        try:
            code = _with_fallback(self._provider, lambda: self._provider.web3.eth.get_code(address))
        except Exception as e:
            rejection = _rpc_rejection_message(e)
            if rejection is not None:
                # The node answered and refused: not a connection failure
                raise ChainConfigurationError(
                    f"The RPC rejected the contract code check: {rejection}"
                ) from e
            if _is_rpc_failure(e):
                # The RPC is at fault, not the contract address
                raise ChainConnectionError(
                    f"The RPC endpoint did not answer the contract code check: {e}",
                    rpc_url=self._provider.rpc_url,
                ) from e
            raise ChainConfigurationError(
                f"Could not check the contract code at {address}: {e}"
            ) from e
        if not code:
            raise ChainConfigurationError(
                f"No contract code at {address} on {self._provider.chain}: "
                f"wrong contract address or chain. Nothing was sent."
            )
        self._contract_code_checked = True

    def _build_tx(self, build, *args, **kwargs) -> dict:
        """
        Call a build_*_tx method and map its errors to chain errors.

        web3's build_transaction runs eth_estimateGas, so a contract revert
        or an RPC failure can happen here, before _send_transaction. Nothing
        has been sent at this point, so no error carries a tx_hash.

        With an explicit gas limit, it is passed to the build method as
        ``gas``, so web3 does not run eth_estimateGas. A transaction that
        would revert is then not caught here: it is sent and costs gas.

        Raises:
            InsufficientFundsError: If the RPC reports insufficient funds.
            ChainTransactionError: If the contract reverts, the RPC answers
                with a JSON-RPC error, or building fails for another reason.
            ChainConnectionError: If the RPC cannot be reached or its answer
                is not JSON-RPC.
        """
        if self._gas_limit is not None:
            kwargs["gas"] = self._gas_limit
        try:
            # Nothing is sent here: building can run again on a fallback RPC
            return _with_fallback(self._provider, lambda: build(*args, **kwargs))
        except ChainError:
            raise
        except Exception as e:
            if _is_contract_revert(e):
                # str() of web3's ContractLogicError is the (message, data)
                # tuple; _error_reason returns the readable revert reason
                reason = _error_reason(e)
                raise ChainTransactionError(f"Transaction reverted: {reason}") from e
            reason = _error_reason(e)
            if "insufficient funds" in reason.lower():
                try:
                    balance_wei = self._wallet.get_balance(self._provider.web3)
                except Exception:
                    balance_wei = None
                raise InsufficientFundsError(
                    f"Insufficient funds for gas: {reason}",
                    wallet_address=self._wallet.address,
                    balance_wei=balance_wei,
                    estimated_cost_wei=0,
                    chain_name=self._provider.chain,
                ) from e
            if _is_rpc_rejection(e):
                # Checked before _is_rpc_failure, which also counts a JSON-RPC
                # error answer as an RPC failure
                reason = _error_reason(e)
                raise ChainTransactionError(f"The RPC rejected the transaction: {reason}") from e
            if _is_rpc_failure(e):
                # Transport only: connection, timeout, or an answer that is not JSON-RPC
                raise ChainConnectionError(
                    f"The RPC endpoint failed while building the transaction: {_error_reason(e)}",
                    rpc_url=self._provider.rpc_url,
                ) from e
            # No "Transaction failed:" prefix: the CLI adds its own
            raise ChainTransactionError(f"Could not build the transaction: {_error_reason(e)}") from e

    def _send_transaction(
        self,
        tx: dict,
        expected_event: str,
        expected_count: int = 1,
        verbose: bool = False,
    ) -> dict:
        """
        Estimate gas, sign, broadcast, wait for receipt, and confirm the event.

        Args:
            tx: Unsigned transaction dict from a build_*_tx method.
            expected_event: Event the contract emits for this write (ABI name).
            expected_count: Number of expected_event events the contract
                must emit (one per item for batch writes).
            verbose: Enable debug output.

        Returns:
            Transaction receipt dict.

        Raises:
            ChainConfigurationError: If the contract address has no code.
            InsufficientFundsError: If wallet balance is too low.
            TransactionNotRecordedError: If the transaction succeeded but the
                contract did not emit expected_count expected_event events.
            TransactionNotVerifiedError: If the transaction was mined but its
                events could not be decoded.
            ChainConnectionError: If the RPC cannot be reached before the
                transaction is sent. Nothing was sent.
            ReceiptTimeoutError: If no receipt arrived within
                RECEIPT_TIMEOUT seconds. The transaction may still be mined.
            TransactionReplacedError: If the receipt wait timed out and
                another transaction with the same nonce was mined instead.
            TransactionOutcomeUnknownError: If the connection to the RPC
                fails after send_raw_transaction was called. The
                transaction may have been sent. The client does not sign
                or send a new transaction (web3's HTTP provider may repeat
                the eth_sendRawTransaction request with the same signed
                bytes, which has the same hash and nonce).
            ChainTransactionError: If transaction fails.
        """
        web3 = self._provider.web3
        # Set just before send_raw_transaction: after that, a transport
        # failure does not mean that nothing was sent
        send_called = False
        raw_tx = None

        self._check_contract_code()

        def prepare():
            # Fill in nonce. "pending" counts this wallet's transactions that
            # are not mined yet, so a second write does not reuse a nonce.
            tx["nonce"] = web3.eth.get_transaction_count(self._wallet.address, "pending")
            tx["chainId"] = self._provider.chain_id

            # Set gas limit: explicit value or estimate with multiplier
            if self._gas_limit is not None:
                tx["gas"] = self._gas_limit
                logger.debug("Using explicit gas limit: %d", self._gas_limit)
            else:
                estimated_gas = web3.eth.estimate_gas(tx)
                tx["gas"] = int(estimated_gas * self._gas_limit_multiplier)
                logger.debug("Estimated gas: %d, limit: %d", estimated_gas, tx["gas"])

            # Pre-flight balance check
            gas_price = tx.get("gasPrice") or web3.eth.gas_price
            estimated_cost = tx["gas"] * gas_price
            self._check_balance(estimated_cost)

        try:
            # Nothing is sent yet, so these steps can run again on a fallback
            # RPC (#168). web3 is the provider's Web3 object, which a switch
            # keeps and points at the new endpoint.
            _with_fallback(self._provider, prepare)

            if verbose:
                print(f"DEBUG: Gas limit: {tx['gas']}")

            # Sign and send
            raw_tx = self._wallet.sign_transaction(tx)
            send_called = True
            tx_hash = web3.eth.send_raw_transaction(raw_tx)

            logger.debug("Transaction sent: %s", tx_hash.hex())
            if verbose:
                print(f"DEBUG: Transaction sent: {tx_hash.hex()}")

            # Wait for the receipt, then check its status and events. The
            # wait may move to a fallback RPC for the same hash; the
            # transaction is never sent again.
            receipt, _ = self._await_receipt(
                tx_hash,
                tx_hash.hex(),
                expected_event,
                expected_count,
                RECEIPT_TIMEOUT,
                sender=self._wallet.address,
                nonce=tx["nonce"],
            )

            logger.debug(
                "Transaction confirmed in block %d, gas used: %d",
                receipt["blockNumber"],
                receipt["gasUsed"],
            )
            if verbose:
                print(f"DEBUG: Confirmed in block {receipt['blockNumber']}, gas: {receipt['gasUsed']}")

            return receipt

        except (ChainTransactionError, InsufficientFundsError):
            raise
        except Exception as e:
            reason = _error_reason(e)
            # Detect "insufficient funds" in RPC error messages and convert.
            # A contract revert is checked first, as in _build_tx: its reason
            # may contain the words without being a funding problem.
            if not _is_contract_revert(e) and "insufficient funds" in reason.lower():
                try:
                    balance_wei = self._wallet.get_balance(self._provider.web3)
                    raise InsufficientFundsError(
                        f"Insufficient funds for gas: {reason}",
                        wallet_address=self._wallet.address,
                        balance_wei=balance_wei,
                        estimated_cost_wei=0,
                        chain_name=self._provider.chain,
                    ) from e
                except InsufficientFundsError:
                    raise
                except Exception:
                    pass  # Fall through to generic handler
            tx_hash_str = None
            if "tx_hash" in dir():
                tx_hash_str = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
            elif send_called:
                # The send raised before it returned the hash: the hash of
                # the signed bytes is the same value
                tx_hash_str = _signed_tx_hash(raw_tx)
            # Transport only: connection, timeout, or an answer that is not
            # JSON-RPC. A JSON-RPC error answer means the node answered. A
            # receipt-wait timeout keeps its own handling.
            if _is_rpc_failure(e) and not _is_rpc_rejection(e) and not _is_receipt_timeout(e):
                if not send_called:
                    raise ChainConnectionError(
                        f"The RPC endpoint failed before the transaction was sent: {reason}",
                        rpc_url=self._provider.rpc_url,
                    ) from e
                # The transaction may have been broadcast: do not sign or
                # send a new one, and do not report it as failed
                raise TransactionOutcomeUnknownError(
                    f"Outcome unknown: transaction {tx_hash_str or '(hash unknown)'} was "
                    f"sent, but the connection to the RPC failed, so its outcome is "
                    f"unknown: {reason}",
                    tx_hash=tx_hash_str,
                    event_name=expected_event,
                    expected_count=expected_count,
                    contract_address=self._contract.address,
                    explorer_url=(
                        self._provider.get_explorer_tx_url(tx_hash_str) if tx_hash_str else None
                    ),
                    reason=reason,
                ) from e
            # No "Transaction failed:" prefix: the CLI adds its own
            raise ChainTransactionError(reason, tx_hash=tx_hash_str) from e

    def _await_receipt(
        self,
        tx_hash,
        tx_hash_str: str,
        expected_event: Optional[str],
        expected_count: int,
        timeout: float,
        sender: Optional[str] = None,
        nonce: Optional[int] = None,
    ):
        """
        Wait for a sent transaction's receipt, then check its status and events (#167).

        Shared by _send_transaction and wait_for_transaction, so a write and
        a resumed wait report a receipt the same way. The wait runs through
        the fallback loop (#168): a transport failure moves the wait to a
        fallback RPC for the same hash.

        On a receipt timeout (web3 TimeExhausted), see _receipt_after_timeout.
        A timeout after the wait moved to a fallback is reported as
        TransactionOutcomeUnknownError, without the nonce check.

        Args:
            tx_hash: The hash as passed to web3 (bytes or hex string).
            tx_hash_str: The hash as reported in errors.
            expected_event: Event the contract must emit, or None to skip
                the event check.
            expected_count: Number of expected_event events.
            timeout: Seconds to wait for the receipt.
            sender: Address that sent the transaction, if known.
            nonce: Nonce of the transaction, if known. Without sender and
                nonce, they are read with get_transaction after a timeout.

        Returns:
            (receipt, emitted): emitted is the number of expected_event
            events, or None when no event check ran.
        """
        web3 = self._provider.web3
        waits = [0]

        def wait_for_receipt():
            waits[0] += 1
            return web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

        try:
            receipt = _with_fallback(self._provider, wait_for_receipt)
        except Exception as e:
            if not _is_receipt_timeout(e):
                raise
            reason = _error_reason(e)
            explorer_url = self._provider.get_explorer_tx_url(tx_hash_str) if tx_hash_str else None
            if waits[0] > 1:
                # The RPC failed during the wait, and the fallback did not
                # return a receipt in time. The transaction was sent and may
                # be mined: do not report it as failed (#168 review)
                raise TransactionOutcomeUnknownError(
                    f"Outcome unknown: transaction {tx_hash_str or '(hash unknown)'} was "
                    f"sent, but the RPC failed while waiting for its receipt, and the "
                    f"fallback RPC did not return the receipt in time, so its outcome "
                    f"is unknown: {reason}",
                    tx_hash=tx_hash_str,
                    event_name=expected_event,
                    expected_count=expected_count,
                    contract_address=self._contract.address,
                    explorer_url=explorer_url,
                    reason=reason,
                ) from e
            receipt = self._receipt_after_timeout(
                e, tx_hash, tx_hash_str, expected_event, expected_count,
                timeout, sender, nonce, explorer_url,
            )

        emitted = self._check_receipt(receipt, tx_hash_str, expected_event, expected_count)
        return receipt, emitted

    def _receipt_after_timeout(
        self,
        error: Exception,
        tx_hash,
        tx_hash_str: str,
        expected_event: Optional[str],
        expected_count: int,
        timeout: float,
        sender: Optional[str],
        nonce: Optional[int],
        explorer_url: Optional[str],
    ):
        """
        Classify a receipt timeout: pending, replaced, or mined after all (#167).

        web3.py has no replacement detection, so the account's mined nonce
        (``get_transaction_count(sender, "latest")``) is compared with the
        transaction's nonce. If it is above, a transaction with this nonce
        was mined: a second receipt lookup then either finds this one's
        receipt (returned, for the normal checks) or nothing (replaced). If a
        lookup fails for another reason, the transaction stays pending.

        Without sender and nonce (a resumed wait), they are read from the
        transaction. If the RPC does not know the transaction,
        TransactionNotFoundError is raised.

        Raises:
            ReceiptTimeoutError: The transaction may still be mined.
            TransactionReplacedError: Another transaction with the same
                nonce was mined instead.
            TransactionNotFoundError: The RPC does not know the transaction.
        """
        web3 = self._provider.web3
        reason = _error_reason(error)
        pending = ReceiptTimeoutError(
            f"Not confirmed yet: transaction {tx_hash_str or '(hash unknown)'} was sent, "
            f"but no receipt arrived within {timeout} seconds. It may still be mined: "
            f"do not send it again. Wait for it with wait_for_transaction(), or check "
            f"it in the block explorer.",
            tx_hash=tx_hash_str,
            event_name=expected_event,
            expected_count=expected_count,
            contract_address=self._contract.address,
            explorer_url=explorer_url,
            reason=reason,
            timeout=timeout,
        )

        if sender is None or nonce is None:
            try:
                tx = web3.eth.get_transaction(tx_hash)
            except Exception as lookup_error:
                if not _is_transaction_not_found(lookup_error):
                    raise pending from error
                tx = None
            if tx is None:
                raise TransactionNotFoundError(
                    f"Not found: the RPC does not know transaction {tx_hash_str}, and "
                    f"no receipt arrived within {timeout} seconds. Check the hash in "
                    f"the block explorer, or read the record back.",
                    tx_hash=tx_hash_str,
                    explorer_url=explorer_url,
                ) from error
            try:
                sender, nonce = tx["from"], tx["nonce"]
            except Exception:
                raise pending from error

        try:
            mined_nonce = web3.eth.get_transaction_count(sender, "latest")
            nonce_used = int(mined_nonce) > int(nonce)
        except Exception:
            raise pending from error
        if not nonce_used:
            raise pending from error

        try:
            receipt = web3.eth.get_transaction_receipt(tx_hash)
        except Exception as lookup_error:
            if not _is_transaction_not_found(lookup_error):
                raise pending from error
            receipt = None
        if receipt is not None:
            # Mined after the wait ended: continue with the normal checks
            return receipt
        raise TransactionReplacedError(
            f"Replaced: transaction {tx_hash_str} was not mined, and another "
            f"transaction with the same nonce ({nonce}) from {sender} was mined "
            f"instead. The other transaction may have made the same write: "
            f"{replaced_check_advice(expected_event)} before you send it again.",
            tx_hash=tx_hash_str,
            event_name=expected_event,
            expected_count=expected_count,
            contract_address=self._contract.address,
            explorer_url=explorer_url,
            nonce=nonce,
        ) from error

    def _check_receipt(
        self,
        receipt,
        tx_hash_str: str,
        expected_event: Optional[str],
        expected_count: int,
    ) -> Optional[int]:
        """
        Require status 1 and, if expected_event is set, its events in the receipt.

        Returns:
            The number of expected_event events, or None without an event check.

        Raises:
            ChainTransactionError: If the transaction reverted (status 0).
            TransactionNotVerifiedError: If the events could not be decoded.
            TransactionNotRecordedError: If the contract did not emit
                expected_count expected_event events.
        """
        if receipt["status"] != 1:
            raise ChainTransactionError(
                "Transaction reverted (status=0)",
                tx_hash=tx_hash_str,
            )
        if expected_event is None:
            return None

        explorer_url = self._provider.get_explorer_tx_url(tx_hash_str) if tx_hash_str else None
        # Status 1 is not enough: a call to an address without the
        # contract also succeeds. Require the contract's own events.
        try:
            emitted = self._contract.count_receipt_events(expected_event, receipt)
        except Exception as e:
            # Mined, so not "Transaction failed": say what is unknown
            raise TransactionNotVerifiedError(
                f"Not verified: transaction {tx_hash_str} was mined, but its "
                f"{expected_event} events could not be verified: {e}",
                tx_hash=tx_hash_str,
                event_name=expected_event,
                expected_count=expected_count,
                contract_address=self._contract.address,
                explorer_url=explorer_url,
                reason=str(e),
            ) from e
        if emitted != expected_count:
            raise TransactionNotRecordedError(
                f"Not recorded: transaction {tx_hash_str} succeeded, but the "
                f"contract at {self._contract.address} emitted {emitted} of "
                f"{expected_count} expected {expected_event} event(s)",
                tx_hash=tx_hash_str,
                event_name=expected_event,
                expected_count=expected_count,
                emitted_count=emitted,
                contract_address=self._contract.address,
                explorer_url=explorer_url,
            )
        return emitted

    @_read_method
    def wait_for_transaction(
        self,
        tx_hash: str,
        expected_event: Optional[str] = None,
        expected_count: int = 1,
        timeout: float = RECEIPT_TIMEOUT,
        verbose: bool = False,
    ) -> TransactionWaitResult:
        """
        Wait for a sent transaction and check its receipt, like a write does (#167).

        Use it to resume after ReceiptTimeoutError. It sends nothing and does
        not need a wallet key. The receipt, status, event and replacement
        checks are the ones a write runs. An unknown hash is polled until
        timeout.

        Args:
            tx_hash: Transaction hash: 64 hex digits, with or without "0x".
            expected_event: Event the contract must emit (an ABI event name),
                or None to skip the event check.
            expected_count: Number of expected_event events.
            timeout: Seconds to wait for the receipt.
            verbose: Enable debug output.

        Returns:
            TransactionWaitResult. event and emitted_count are None when no
            event check ran.

        Raises:
            ChainValidationError: If an argument is not valid.
            ChainTransactionError: If the transaction reverted.
            TransactionNotRecordedError, TransactionNotVerifiedError: As for
                a write.
            ReceiptTimeoutError: If no receipt arrived within timeout.
            TransactionReplacedError: If another transaction with the same
                nonce was mined instead.
            TransactionNotFoundError: If the RPC does not know the hash after
                the wait.
            ChainConnectionError: If no RPC endpoint can be reached.

        A transport failure runs the whole wait again on a fallback RPC
        (#168), with the full timeout, so the total wait can be longer than
        timeout. A timeout on the fallback then gets the nonce check, as
        without a switch.
        """
        import re
        from ..chain.contract import abi_event_names

        if not isinstance(tx_hash, str) or not re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", tx_hash.strip()):
            raise ChainValidationError(
                "Transaction hash must be 64 hex digits, with or without 0x"
            )
        tx_hash = tx_hash.strip()
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        if expected_event is not None and expected_event not in abi_event_names():
            raise ChainValidationError(
                f"Unknown event {expected_event!r}. Events: {', '.join(abi_event_names())}"
            )
        if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 1:
            raise ChainValidationError("expected_count must be 1 or more")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ChainValidationError("timeout must be more than 0 seconds")

        logger.debug("Wait for transaction %s (event %s x%d)", tx_hash, expected_event, expected_count)
        receipt, emitted = self._await_receipt(
            tx_hash, tx_hash, expected_event, expected_count, timeout,
        )
        if verbose:
            print(f"DEBUG: Confirmed in block {receipt['blockNumber']}, gas: {receipt['gasUsed']}")
        return TransactionWaitResult(
            tx_hash=tx_hash,
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            status=receipt["status"],
            explorer_url=self._provider.get_explorer_tx_url(tx_hash),
            event=expected_event,
            emitted_count=emitted,
        )

    def _receipt_to_explorer_url(self, receipt: dict) -> Optional[str]:
        """Get explorer URL from a transaction receipt."""
        tx_hash = receipt.get("transactionHash")
        if tx_hash:
            return self._provider.get_explorer_tx_url(tx_hash.hex())
        return None

    # --- Write operations ---

    @_write_method
    def anchor(
        self,
        swarm_hash: str,
        data_type: str = "swarm-provenance",
        storage_ref: Optional[str] = None,
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Anchor a Swarm hash on-chain by registering it in the DataProvenance contract.

        Args:
            swarm_hash: Swarm reference hash (64 hex chars).
            data_type: Data type/category (max 64 chars, default 'swarm-provenance').
            storage_ref: Optional storage reference (e.g. Swarm hash) to link
                bidirectionally with the data hash.
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        logger.debug("Anchor: hash=%s type=%s storage_ref=%s", swarm_hash, data_type, storage_ref)

        # A read from an address without code fails with an unclear error:
        # check the code first so the user gets "No contract code"
        self._check_contract_code()

        # Pre-check: avoid wasting gas on already-registered hashes
        try:
            record = self.get(swarm_hash, verbose=verbose)
            raise DataAlreadyRegisteredError(
                f"Data hash {swarm_hash} is already registered on-chain",
                data_hash=swarm_hash,
                owner=record.owner,
                timestamp=record.timestamp,
                data_type=record.data_type,
            )
        except DataNotRegisteredError:
            pass  # Not registered — proceed with anchoring

        try:
            # Inside the try: an "already registered" revert usually shows up
            # in gas estimation, which building the transaction runs
            tx = self._build_tx(
                self._contract.build_register_data_tx,
                data_hash=swarm_hash,
                data_type=data_type,
                sender=self._wallet.address,
                storage_ref=storage_ref,
            )
            receipt = self._send_transaction(tx, "DataRegistered", verbose=verbose)
        except ChainTransactionError as e:
            # Detect "already registered" revert that the pre-check missed
            # (can happen when public RPC serves stale reads)
            if "already registered" in str(e).lower():
                try:
                    record = self.get(swarm_hash, verbose=verbose)
                    raise DataAlreadyRegisteredError(
                        f"Data hash {swarm_hash} is already registered on-chain",
                        data_hash=swarm_hash,
                        owner=record.owner,
                        timestamp=record.timestamp,
                        data_type=record.data_type,
                    ) from e
                except DataNotRegisteredError:
                    pass  # Still not visible — re-raise original
            raise

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type=data_type,
            owner=self._wallet.address,
            storage_ref=storage_ref,
        )

    @_write_method
    def anchor_for(
        self,
        swarm_hash: str,
        owner: str,
        data_type: str = "swarm-provenance",
        storage_ref: Optional[str] = None,
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Anchor a Swarm hash on behalf of another owner.

        Caller must be an authorized delegate of the owner.

        Args:
            swarm_hash: Swarm reference hash.
            owner: Address of the actual data owner.
            data_type: Data type/category.
            storage_ref: Optional storage reference to link with the data hash.
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        logger.debug("Anchor for: hash=%s owner=%s", swarm_hash, owner)

        # A read from an address without code fails with an unclear error:
        # check the code first so the user gets "No contract code"
        self._check_contract_code()

        # Pre-check: avoid wasting gas on already-registered hashes
        try:
            record = self.get(swarm_hash, verbose=verbose)
            raise DataAlreadyRegisteredError(
                f"Data hash {swarm_hash} is already registered on-chain",
                data_hash=swarm_hash,
                owner=record.owner,
                timestamp=record.timestamp,
                data_type=record.data_type,
            )
        except DataNotRegisteredError:
            pass  # Not registered — proceed with anchoring

        tx = self._build_tx(
            self._contract.build_register_data_for_tx,
            data_hash=swarm_hash,
            data_type=data_type,
            actual_owner=owner,
            sender=self._wallet.address,
            storage_ref=storage_ref,
        )
        receipt = self._send_transaction(tx, "DataRegistered", verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type=data_type,
            owner=owner,
            storage_ref=storage_ref,
        )

    @_write_method
    def batch_anchor(
        self,
        swarm_hashes: List[str],
        data_types: List[str],
        storage_refs: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Anchor multiple Swarm hashes in a single transaction.

        Args:
            swarm_hashes: List of Swarm reference hashes.
            data_types: List of data type strings (same length).
            storage_refs: Optional list of storage references (same length).
            verbose: Enable debug output.

        Returns:
            AnchorResult for the batch transaction (swarm_hash is first hash).
        """
        logger.debug("Batch anchor: count=%d", len(swarm_hashes))

        tx = self._build_tx(
            self._contract.build_batch_register_data_tx,
            data_hashes=swarm_hashes,
            data_types=data_types,
            sender=self._wallet.address,
            storage_refs=storage_refs,
        )
        receipt = self._send_transaction(
            tx, "DataRegistered", expected_count=len(swarm_hashes), verbose=verbose
        )

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hashes[0] if swarm_hashes else "",
            data_type=data_types[0] if data_types else "",
            owner=self._wallet.address,
        )

    @_write_method
    def set_storage_ref(
        self,
        data_hash: str,
        storage_ref: str,
        verbose: bool = False,
    ) -> AnchorResult:
        """
        Set the storage reference for an existing on-chain record.

        This is a set-once operation — once set, the storage ref is immutable.

        Args:
            data_hash: Registered data hash (64 hex chars).
            storage_ref: Storage reference to link (e.g. Swarm hash, 64 hex chars).
            verbose: Enable debug output.

        Returns:
            AnchorResult with transaction details.
        """
        logger.debug("Set storage ref: hash=%s ref=%s", data_hash, storage_ref)

        tx = self._build_tx(
            self._contract.build_set_storage_ref_tx,
            data_hash=data_hash,
            storage_ref=storage_ref,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, "StorageRefLinked", verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=data_hash,
            data_type="",
            owner=self._wallet.address,
            storage_ref=storage_ref,
        )

    @_read_method
    def get_by_storage_ref(
        self,
        storage_ref: str,
        verbose: bool = False,
    ) -> ChainProvenanceRecord:
        """
        Look up a provenance record by its storage reference.

        Args:
            storage_ref: Storage reference hash (64 hex chars).
            verbose: Enable debug output.

        Returns:
            ChainProvenanceRecord for the linked data hash.

        Raises:
            DataNotRegisteredError: If no record is linked to this storage ref.
        """
        logger.debug("Lookup by storage ref: %s", storage_ref)
        data_hash_bytes = self._contract.get_data_hash_by_storage_ref(storage_ref)
        if data_hash_bytes is None:
            raise DataNotRegisteredError(
                f"No data record linked to storage ref {storage_ref}",
                data_hash=storage_ref,
            )
        data_hash = data_hash_bytes.hex()
        return self.get(data_hash, verbose=verbose)

    @_write_method
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
        logger.debug(
            "Transform: original=%s new=%s desc=%s",
            original_hash,
            new_hash,
            description,
        )

        # Pre-check: avoid wasting gas on duplicate transformations.
        # Prefer state read on v2 contracts, fall back to event cache.
        # Transport failures go through the fallbacks; when no endpoint is
        # left, the write stops before anything is sent (#168). Other errors
        # are logged and the write goes on. The contract version probe runs
        # through the fallbacks too, so a dead RPC is not taken as a v1
        # contract, which would skip the check (#230).
        try:
            is_v2 = _with_fallback(
                self._provider, lambda: self._contract.supports_transformation_links()
            )
        except Exception as e:
            if _is_transport_failure(e):
                raise _duplicate_check_connection_error(e, self._provider.rpc_url) from e
            logger.warning(
                "Duplicate transformation check skipped: the contract version check failed: %s",
                redact_urls(_error_reason(e)),
            )
            is_v2 = None
        if is_v2 is None:
            pass
        elif is_v2:
            try:
                links = _with_fallback(
                    self._provider,
                    lambda: self._contract.get_transformation_links(original_hash),
                )
                for existing_new, existing_desc in links:
                    existing_hex = (
                        existing_new.hex()
                        if isinstance(existing_new, bytes)
                        else str(existing_new)
                    )
                    if existing_hex == new_hash:
                        raise TransformationAlreadyExistsError(
                            f"Transformation {original_hash[:16]}... -> {new_hash[:16]}... already exists",
                            original_hash=original_hash,
                            new_hash=new_hash,
                            existing_description=existing_desc,
                        )
            except TransformationAlreadyExistsError:
                raise
            except Exception as e:
                if _is_transport_failure(e):
                    raise _duplicate_check_connection_error(e, self._provider.rpc_url) from e
                logger.warning("State-based duplicate check failed: %s", redact_urls(str(e)))
        else:
            deploy_block = self._provider.deploy_block
            if deploy_block is None:
                logger.warning(
                    "Duplicate transformation check skipped: the contract has no "
                    "transformation links and its deploy block is unknown."
                )
            else:
                try:
                    from ..chain.event_cache import get_cache

                    cache = get_cache(
                        self._provider.chain, self._provider.contract_address
                    )
                    # The block number and the event scan (chunked
                    # eth_getLogs) run again on a fallback together
                    def scan():
                        current_block = self._provider.web3.eth.block_number
                        return cache.get_maps(self._contract, deploy_block, current_block)

                    forward, _ = _with_fallback(self._provider, scan)
                    for existing_new, existing_desc in forward.get(original_hash, []):
                        if existing_new == new_hash:
                            raise TransformationAlreadyExistsError(
                                f"Transformation {original_hash[:16]}... -> {new_hash[:16]}... already exists",
                                original_hash=original_hash,
                                new_hash=new_hash,
                                existing_description=existing_desc,
                            )
                except TransformationAlreadyExistsError:
                    raise
                except Exception as e:
                    if _is_transport_failure(e):
                        raise _duplicate_check_connection_error(e, self._provider.rpc_url) from e
                    logger.warning("Duplicate check failed, proceeding: %s", redact_urls(str(e)))

        tx = self._build_tx(
            self._contract.build_record_transformation_tx,
            original_hash=original_hash,
            new_hash=new_hash,
            description=description,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, "DataTransformed", verbose=verbose)

        return TransformResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            original_hash=original_hash,
            new_hash=new_hash,
            description=description,
        )

    @_write_method
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
        logger.debug("Record access: hash=%s", swarm_hash)

        tx = self._build_tx(
            self._contract.build_record_access_tx,
            data_hash=swarm_hash,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, "DataAccessed", verbose=verbose)

        return AccessResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            accessor=self._wallet.address,
        )

    @_write_method
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
        logger.debug("Batch access: count=%d", len(swarm_hashes))

        tx = self._build_tx(
            self._contract.build_batch_record_access_tx,
            data_hashes=swarm_hashes,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(
            tx, "DataAccessed", expected_count=len(swarm_hashes), verbose=verbose
        )

        return AccessResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hashes[0] if swarm_hashes else "",
            accessor=self._wallet.address,
        )

    @_write_method
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
        logger.debug(
            "Set status: hash=%s status=%s", swarm_hash, DataStatus(status).name
        )

        tx = self._build_tx(
            self._contract.build_set_data_status_tx,
            data_hash=swarm_hash,
            status=status,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, "DataStatusChanged", verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type="",
            owner=self._wallet.address,
        )

    @_write_method
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
        logger.debug("Batch set status: count=%d", len(swarm_hashes))

        tx = self._build_tx(
            self._contract.build_batch_set_data_status_tx,
            data_hashes=swarm_hashes,
            statuses=statuses,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(
            tx, "DataStatusChanged", expected_count=len(swarm_hashes), verbose=verbose
        )

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hashes[0] if swarm_hashes else "",
            data_type="",
            owner=self._wallet.address,
        )

    @_write_method
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
        logger.debug("Transfer ownership: hash=%s new_owner=%s", swarm_hash, new_owner)

        tx = self._build_tx(
            self._contract.build_transfer_ownership_tx,
            data_hash=swarm_hash,
            new_owner=new_owner,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, "DataOwnershipTransferred", verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash=swarm_hash,
            data_type="",
            owner=new_owner,
        )

    @_write_method
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
        action = "Authorize" if authorized else "Revoke"
        logger.debug("%s delegate: %s", action, delegate)

        tx = self._build_tx(
            self._contract.build_set_delegate_tx,
            delegate=delegate,
            authorized=authorized,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, "DelegateAuthorized", verbose=verbose)

        return AnchorResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            swarm_hash="",
            data_type="",
            owner=self._wallet.address,
        )

    @_write_method
    def merge_transform(
        self,
        source_hashes: List[str],
        new_hash: str,
        description: str,
        new_data_type: str = "merged",
        verbose: bool = False,
    ) -> MergeTransformResult:
        """
        Record an N-to-1 merge transformation on-chain.

        All source hashes must be registered. The new_hash is registered
        automatically by the contract.

        Args:
            source_hashes: List of original data hashes (2-50).
            new_hash: Hash of the merged data.
            description: Transformation description (max 256 chars).
            new_data_type: Data type for merged result (max 64 chars).
            verbose: Enable debug output.

        Returns:
            MergeTransformResult with transaction details.
        """
        logger.debug(
            "Merge transform: sources=%d new=%s desc=%s",
            len(source_hashes),
            new_hash,
            description,
        )

        tx = self._build_tx(
            self._contract.build_record_merge_transformation_tx,
            source_hashes=source_hashes,
            new_hash=new_hash,
            description=description,
            new_data_type=new_data_type,
            sender=self._wallet.address,
        )
        receipt = self._send_transaction(tx, "DataMerged", verbose=verbose)

        return MergeTransformResult(
            tx_hash=receipt["transactionHash"].hex(),
            block_number=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
            explorer_url=self._receipt_to_explorer_url(receipt),
            source_hashes=source_hashes,
            new_hash=new_hash,
            description=description,
            new_data_type=new_data_type,
        )

    # --- Read operations ---

    @_read_method
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
        logger.debug("Get record: hash=%s", swarm_hash)

        record = self._contract.get_data_record(swarm_hash)

        # record is a tuple: (dataHash, owner, timestamp, dataType,
        #                      storageRef, transformationLinks, accessors, status)
        (
            data_hash_bytes,
            owner,
            timestamp,
            data_type,
            storage_ref_bytes,
            transformations,
            accessors,
            status,
        ) = record

        # Check if data is registered (owner is zero address if not)
        zero_address = "0x" + "0" * 40
        if owner == zero_address:
            raise DataNotRegisteredError(
                f"Data hash {swarm_hash} is not registered on-chain",
                data_hash=swarm_hash,
            )

        # Parse storage ref — bytes32(0) means not set
        storage_ref = None
        if isinstance(storage_ref_bytes, bytes) and storage_ref_bytes != b"\x00" * 32:
            storage_ref = storage_ref_bytes.hex()

        # Parse transformations — v2+ contracts return TransformationLink[]
        # (list of (bytes32, string) tuples), v1 returns string[].
        chain_transformations = []
        for t in transformations:
            if isinstance(t, (tuple, list)) and len(t) >= 2:
                # V2+ contract: TransformationLink(newDataHash, description)
                new_hash = t[0].hex() if isinstance(t[0], bytes) else str(t[0])
                chain_transformations.append(
                    ChainTransformation(description=str(t[1]), new_data_hash=new_hash)
                )
            else:
                # V1 contract: plain string description
                chain_transformations.append(ChainTransformation(description=str(t)))

        logger.debug(
            "Record: owner=%s type=%s status=%s accessors=%d storage_ref=%s",
            owner,
            data_type,
            DataStatus(status).name,
            len(accessors),
            storage_ref,
        )

        if verbose:
            print(f"DEBUG: Owner: {owner}")
            print(f"DEBUG: Type: {data_type}")
            print(f"DEBUG: Status: {DataStatus(status).name}")
            print(f"DEBUG: Accessors: {len(accessors)}")
            if storage_ref:
                print(f"DEBUG: Storage Ref: {storage_ref}")

        return ChainProvenanceRecord(
            data_hash=(
                data_hash_bytes.hex()
                if isinstance(data_hash_bytes, bytes)
                else str(data_hash_bytes)
            ),
            owner=owner,
            timestamp=timestamp,
            data_type=data_type,
            storage_ref=storage_ref,
            status=DataStatusEnum(status),
            accessors=list(accessors),
            transformations=chain_transformations,
        )

    @_read_method
    def verify(
        self,
        swarm_hash: str,
        verbose: bool = False,
    ) -> bool:
        """
        Verify that a Swarm hash is registered on-chain.

        This checks registration only: a RESTRICTED or DELETED record, or
        one owned by any address, still returns True. Use get() to check
        the record's status and owner.

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

    @_read_method
    def balance(self, verbose: bool = False) -> ChainWalletInfo:
        """
        Get wallet balance and chain info.

        Args:
            verbose: Enable debug output.

        Returns:
            ChainWalletInfo with balance and chain details.
        """
        logger.debug("Balance check")

        balance_wei = self._wallet.get_balance(self._provider.web3)
        balance_eth = self._wallet.get_balance_eth(self._provider.web3)

        logger.debug("Address: %s Balance: %s ETH", self._wallet.address, balance_eth)

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

    @_read_method
    def health_check(self, verbose: bool = False) -> bool:
        """
        Check if the chain provider is connected and healthy.

        Args:
            verbose: Enable debug output.

        Returns:
            True if healthy.

        Raises:
            ChainIdMismatchError: If the RPC in use reports another chain ID.
                No fallback is tried in this case.
            ChainConnectionError: If health check fails.
        """
        logger.debug(
            "Chain health check: chain=%s rpc=%s",
            self._provider.chain,
            redact_url(self._provider.rpc_url),
        )

        result = self._provider.health_check()

        logger.debug("Connected, block: %d", self._provider.get_block_number())

        if verbose:
            block = self._provider.get_block_number()
            print(f"DEBUG: Connected, block: {block}")

        return result

    @_read_method
    def get_provenance_chain(
        self,
        swarm_hash: str,
        max_depth: Optional[int] = None,
        verbose: bool = False,
    ) -> List[ChainProvenanceRecord]:
        """
        Get the provenance chain for a data hash.

        On v2 contracts, uses state reads (``getTransformationLinks`` /
        ``getTransformationParents``) for traversal — no event scanning.
        On v1 contracts, falls back to the cached event scan path.
        Falls back to per-node event scanning when the deploy block is unknown.

        The walk fails closed: if any read fails, the call raises instead of
        returning the nodes reached so far (#170).

        Args:
            swarm_hash: Starting Swarm reference hash.
            max_depth: Maximum traversal depth, 0 to 50 (0 returns the start
                node only). None means the default of 10. Nodes at
                max_depth are returned but not expanded: their ``parents``
                is None.
            verbose: Enable debug output.

        Returns:
            List of ChainProvenanceRecord forming the provenance chain,
            starting with the given hash, in breadth-first order. Each
            expanded node carries its parent hashes in ``parents``. An
            unregistered start hash returns an empty list.

        Raises:
            ChainValidationError: If max_depth is outside 0 to 50.
            ChainConnectionError: If an RPC read fails during the walk.
            ChainError: If another read fails during the walk, or a linked
                hash reads as not registered.
        """
        logger.debug(
            "Get provenance chain: hash=%s max_depth=%s", swarm_hash, max_depth
        )

        if max_depth is None:
            effective_max = DEFAULT_CHAIN_DEPTH
        elif (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, int)
            or not 0 <= max_depth <= MAX_CHAIN_DEPTH
        ):
            raise ChainValidationError(
                f"max_depth must be an integer from 0 to {MAX_CHAIN_DEPTH}, got {max_depth!r}"
            )
        else:
            effective_max = max_depth

        # Detect contract version — state reads are much faster than event
        # scans. A probe error fails the walk like any other read (#230):
        # a transport failure moves to a fallback (this method's read loop),
        # and is never taken as a v1 contract.
        use_state_reads = self._contract.supports_transformation_links()

        # Fall back to event cache for v1 contracts
        from ..chain.event_cache import get_cache

        forward = {}  # original_hex -> [(new_hex, desc)]
        reverse = {}  # new_hex -> [(original_hex, desc)]
        deploy_block = self._provider.deploy_block
        use_local_index = False

        if not use_state_reads and deploy_block is not None:
            try:
                cache = get_cache(self._provider.chain, self._provider.contract_address)
                current_block = self._provider.web3.eth.block_number
                forward, reverse = cache.get_maps(
                    self._contract, deploy_block, current_block
                )
                use_local_index = True
            except Exception as e:
                logger.warning(
                    "Full event scan failed, falling back to per-node queries: %s",
                    redact_urls(str(e)),
                )

        def _hex(value) -> str:
            return value.hex() if isinstance(value, bytes) else str(value)

        # Child and parent hashes come back as lower-case hex without 0x.
        # Key the start hash the same way, or it is visited twice and the
        # event index misses its edges.
        start_hash = swarm_hash
        if isinstance(start_hash, str):
            start_hash = start_hash.lower()
            if start_hash.startswith("0x"):
                start_hash = start_hash[2:]

        chain = []
        visited = set()
        to_visit = [(start_hash, 0)]

        while to_visit:
            current_hash, current_depth = to_visit.pop(0)
            if current_hash in visited:
                continue
            visited.add(current_hash)

            try:
                record = self.get(current_hash, verbose=verbose)
            except DataNotRegisteredError as e:
                if current_depth == 0:
                    logger.debug("Hash %s not registered", current_hash)
                    continue
                raise _traversal_error(current_hash, current_depth, e) from _traversal_cause(e)
            except Exception as e:
                logger.debug(
                    "Record read failed for %s: %s", current_hash, redact_urls(str(e))
                )
                raise _traversal_error(current_hash, current_depth, e) from _traversal_cause(e)

            # Nodes at the depth limit keep their child edges but are not
            # expanded: parents are not read and stay None.
            expand = current_depth < effective_max
            parents = None
            try:
                if use_state_reads:
                    # V2 contract: state-based traversal
                    links = self._contract.get_transformation_links(current_hash)
                    if links:
                        record.transformations = [
                            ChainTransformation(description=desc, new_data_hash=_hex(nh))
                            for nh, desc in links
                        ]
                    children = [_hex(nh) for nh, _ in links]
                    if expand:
                        parents = [
                            _hex(p)
                            for p in self._contract.get_transformation_parents(current_hash)
                        ]
                elif use_local_index:
                    # V1 contract: use pre-built event cache index
                    fwd = forward.get(current_hash, [])
                    if fwd:
                        record.transformations = [
                            ChainTransformation(description=desc, new_data_hash=nh)
                            for nh, desc in fwd
                        ]
                    children = [nh for nh, _ in fwd]
                    if expand:
                        parents = [orig for orig, _ in reverse.get(current_hash, [])]
                else:
                    # Per-node event scanning (fallback when deploy_block unknown)
                    events = self._contract.get_transformations_from(current_hash)
                    enriched = [
                        ChainTransformation(description=desc, new_data_hash=_hex(new_bytes))
                        for _, new_bytes, desc in events
                    ]
                    if enriched:
                        record.transformations = enriched
                    children = [t.new_data_hash for t in enriched]
                    if expand:
                        parents = [
                            _hex(orig_bytes)
                            for orig_bytes, _, _ in self._contract.get_transformations_to(current_hash)
                        ]
            except Exception as e:
                logger.debug(
                    "Link read failed for %s: %s", current_hash, redact_urls(str(e))
                )
                raise _traversal_error(current_hash, current_depth, e) from _traversal_cause(e)

            chain.append(record)

            if not expand:
                logger.debug("Depth limit reached at %d", current_depth)
                continue

            record.parents = list(dict.fromkeys(parents))
            for next_hash in children + record.parents:
                if next_hash not in visited:
                    to_visit.append((next_hash, current_depth + 1))

        logger.debug("Chain length: %d", len(chain))

        if verbose:
            print(f"DEBUG: Chain length: {len(chain)}")

        return chain
