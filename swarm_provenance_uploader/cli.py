import typer
from typing import Optional
from typing_extensions import Annotated
from pathlib import Path
import sys
import time
import json
import warnings

from . import config, __version__
from .core import file_utils, swarm_client, metadata_builder
from .core.gateway_client import GatewayClient
from .models import ProvenanceMetadata, ValidationError
from . import exceptions

app = typer.Typer(help="Swarm Provenance CLI - Wraps and uploads data to Swarm.")
stamps_app = typer.Typer(help="Manage postage stamps.")
app.add_typer(stamps_app, name="stamps")
x402_app = typer.Typer(help="x402 payment configuration and status.")
app.add_typer(x402_app, name="x402")
notary_app = typer.Typer(help="Notary signing service commands.")
app.add_typer(notary_app, name="notary")
chain_app = typer.Typer(help="On-chain provenance anchoring (optional).")
app.add_typer(chain_app, name="chain")


def _version_callback(value: bool):
    """Print version and exit."""
    if value:
        typer.echo(f"swarm-prov-upload {__version__}")
        raise typer.Exit()


def _show_local_backend_warning():
    """Show deprecation warning for local backend usage."""
    if not _backend_config.get("_warning_shown"):
        typer.secho(
            "\n⚠️  Note: Local Bee backend is intended for development/testing.",
            fg=typer.colors.YELLOW,
            err=True
        )
        typer.secho(
            "   For production use, consider the gateway: --backend gateway\n",
            fg=typer.colors.YELLOW,
            err=True
        )
        _backend_config["_warning_shown"] = True

# Global state for backend configuration
_backend_config = {
    "backend": config.BACKEND,
    "gateway_url": config.GATEWAY_URL,
    "bee_url": config.BEE_GATEWAY_URL,
    "free_tier": config.FREE_TIER,
}

# Global state for x402 payment configuration
_x402_config = {
    "enabled": config.X402_ENABLED,
    "auto_pay": config.X402_AUTO_PAY,
    "max_auto_pay_usd": config.X402_MAX_AUTO_PAY_USD,
    "network": config.X402_NETWORK,
}

# Global state for chain / blockchain configuration
_chain_config = {
    "enabled": config.CHAIN_ENABLED,
    "chain": config.CHAIN_NAME,
    "rpc_url": config.CHAIN_RPC_URL,
    "contract": config.CHAIN_CONTRACT,
    "wallet_key_env": config.CHAIN_WALLET_KEY_ENV,
    "explorer_url": config.CHAIN_EXPLORER_URL,
    "gas_limit": config.CHAIN_GAS_LIMIT,
}


def _get_chain_client(verbose: bool = False):
    """
    Create a ChainClient with current chain configuration.

    Args:
        verbose: Enable verbose output.

    Returns:
        Configured ChainClient instance.

    Raises:
        typer.Exit: If dependencies are missing or config is invalid.
    """
    try:
        from .core.chain_client import ChainClient
    except ImportError:
        typer.secho(
            "ERROR: Blockchain dependencies not installed.",
            fg=typer.colors.RED, err=True,
        )
        typer.echo("Install with: pip install swarm-provenance-uploader[blockchain]")
        raise typer.Exit(code=1)

    try:
        return ChainClient(
            chain=_chain_config["chain"],
            rpc_url=_chain_config["rpc_url"],
            contract_address=_chain_config["contract"],
            private_key_env=_chain_config["wallet_key_env"],
            explorer_url=_chain_config["explorer_url"],
            gas_limit=_chain_config.get("gas_limit"),
        )
    except exceptions.ChainConfigurationError as e:
        typer.secho(f"ERROR: Chain configuration invalid: {e}", fg=typer.colors.RED, err=True)
        typer.echo("Check PROVENANCE_WALLET_KEY environment variable and chain settings.")
        raise typer.Exit(code=1)


def _x402_payment_callback(amount_usd: str, description: str) -> bool:
    """
    Callback for x402 payment confirmation prompts.

    Args:
        amount_usd: Formatted amount string (e.g., "$0.05")
        description: Description of what the payment is for

    Returns:
        True if user confirms, False otherwise
    """
    typer.echo("")
    typer.secho(f"Payment required: {amount_usd} USDC", fg=typer.colors.YELLOW, bold=True)
    typer.echo(f"  For: {description}")
    typer.echo(f"  Network: {_x402_config['network']}")

    # Prompt for confirmation
    confirm = typer.confirm("Pay now?", default=True)
    if confirm:
        typer.echo("Processing payment...")
    return confirm


def _get_gateway_client_with_x402(gateway_url: str, verbose: bool = False) -> GatewayClient:
    """
    Create a GatewayClient with x402 configuration if enabled.

    Args:
        gateway_url: Gateway URL
        verbose: Verbose mode

    Returns:
        Configured GatewayClient
    """
    if _x402_config["enabled"]:
        if verbose:
            typer.echo(f"    x402 payments enabled ({_x402_config['network']})")

        return GatewayClient(
            base_url=gateway_url,
            x402_enabled=True,
            x402_network=_x402_config["network"],
            x402_auto_pay=_x402_config["auto_pay"],
            x402_max_auto_pay_usd=_x402_config["max_auto_pay_usd"],
            x402_payment_callback=_x402_payment_callback,
            free_tier=_backend_config["free_tier"],
        )
    else:
        return GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])

@app.command()
def upload(
    file: Annotated[Path, typer.Option(
        ...,
        "--file",
        "-f",
        help="Path to the provenance data file to wrap and upload.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        )
     ],
    provenance_standard: Annotated[Optional[str], typer.Option("--std", help="Identifier for the provenance standard used (optional).")] = None,
    encryption: Annotated[Optional[str], typer.Option("--enc", help="Details about encryption used (optional).")] = None,
    bee_url: Annotated[Optional[str], typer.Option("--bee-url", help="Bee Gateway URL (when backend=local).")] = None,
    stamp_id: Annotated[Optional[str], typer.Option("--stamp-id", "-s", help="Existing stamp ID to reuse (skips stamp purchase).")] = None,
    duration: Annotated[Optional[int], typer.Option("--duration", "-d", help="Stamp validity in hours (min 24, gateway only).")] = None,
    size: Annotated[Optional[str], typer.Option("--size", help="Stamp size preset: 'small', 'medium', 'large' (gateway only).")] = None,
    stamp_depth: Annotated[Optional[int], typer.Option("--depth", help="Postage stamp depth (16-32).")] = None,
    stamp_amount: Annotated[Optional[int], typer.Option("--amount", help="Legacy: PLUR amount (local backend or deprecated).")] = None,
    stamp_check_retries: Annotated[int, typer.Option("--stamp-retries", help="Number of times to check for stamp usability.")] = 12,
    stamp_check_interval: Annotated[int, typer.Option("--stamp-interval", help="Seconds to wait between stamp usability checks.")] = 20,
    use_pool: Annotated[bool, typer.Option("--usePool", help="Acquire stamp from pool instead of purchasing (gateway only, faster ~5s vs >1min).")] = False,
    sign: Annotated[Optional[str], typer.Option("--sign", help="Sign document with notary service. Value: 'notary' (gateway only).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output for debugging.")] = False
):
    """
    Hashes, Base64-encodes, wraps, and Uploads a
    provenance data file to Swarm.

    By default purchases a new stamp with 25 hours validity.
    Use --stamp-id to reuse an existing stamp.
    Use --duration to specify validity in hours (min 24).
    Use --size for preset sizes: small, medium, large.
    Use --usePool to acquire from pool (faster, gateway only).
    Use --sign notary to add a notary signature (gateway only).
    """
    # Determine which backend to use
    use_gateway = _backend_config["backend"] == "gateway"
    gateway_url = _backend_config["gateway_url"]
    local_bee_url = bee_url or _backend_config["bee_url"]

    # Validate --sign option
    use_signing = False
    if sign:
        if sign.lower() != "notary":
            typer.secho(f"ERROR: Invalid --sign value '{sign}'. Use 'notary'.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        if not use_gateway:
            typer.secho("ERROR: --sign requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        use_signing = True

    # Show warning for local backend
    if not use_gateway:
        _show_local_backend_warning()

    if verbose:
        typer.echo("Verbose mode enabled.")
        typer.echo(f"--> Initial Config:")
        typer.echo(f"    Backend: {_backend_config['backend']}")
        typer.echo(f"    File: {file}")
        if use_gateway:
            typer.echo(f"    Gateway URL: {gateway_url}")
            if duration:
                typer.echo(f"    Duration: {duration} hours")
            if size:
                typer.echo(f"    Size: {size}")
        else:
            typer.echo(f"    Bee URL: {local_bee_url}")
            if stamp_amount:
                typer.echo(f"    Stamp Amount: {stamp_amount}")
        if stamp_depth:
            typer.echo(f"    Stamp Depth: {stamp_depth}")
        typer.echo(f"    Stamp Check Retries: {stamp_check_retries}")
        typer.echo(f"    Stamp Check Interval: {stamp_check_interval}s")
        if use_pool:
            typer.echo(f"    Use Pool: Yes (acquire from pool instead of purchasing)")
        if use_signing:
            typer.echo(f"    Sign: notary (document will be signed by gateway notary)")
    else:
        typer.echo(f"Processing file: {file.name}...")


    # 1-4. Read file, hash, base64, estimate size
    try:
        raw_content = file_utils.read_file_content(file)
    except Exception as e:
        typer.secho(f"ERROR: Failed reading file '{file.name}': {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    sha256_hash = file_utils.calculate_sha256(raw_content)
    if verbose:
        typer.echo(f"    SHA256 Hash: {sha256_hash}")
    b64_encoded_data = file_utils.base64_encode_data(raw_content)

    try:
       temp_metadata_for_size_calc = metadata_builder.create_provenance_metadata_object(
            base64_data=b64_encoded_data, content_hash=sha256_hash, stamp_id="0"*64,
            provenance_standard=provenance_standard, encryption=encryption )
       payload_to_upload_bytes = metadata_builder.serialize_metadata_to_bytes(temp_metadata_for_size_calc)
       # payload_size = file_utils.get_data_size(payload_to_upload_bytes) # Not strictly needed for user output unless verbose
       # if verbose:
       #     typer.echo(f"    Estimated Metadata Payload Size: {payload_size} bytes")
    except Exception as e:
       typer.secho(f"ERROR: Failed preparing metadata structure: {e}", fg=typer.colors.RED, err=True)
       raise typer.Exit(code=1)

    # 5 & 6. Request postage stamp OR use existing one OR acquire from pool
    used_existing_stamp = False
    acquired_from_pool = False
    if stamp_id:
        # User provided an existing stamp ID
        used_existing_stamp = True
        typer.echo(f"Using existing stamp: ...{stamp_id[-12:]}")
        if verbose:
            typer.echo(f"    Stamp ID: {stamp_id}")
    elif use_pool:
        # Acquire stamp from pool (gateway only)
        if not use_gateway:
            typer.secho("ERROR: --usePool requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Acquiring stamp from pool...")
        if verbose:
            typer.echo(f"    (Size: {size or 'default'}, Depth: {stamp_depth or 'default'} from {gateway_url})")

        try:
            gw_client = _get_gateway_client_with_x402(gateway_url, verbose)

            # First check pool availability
            available_count = gw_client.get_pool_available_count(size=size, depth=stamp_depth, verbose=verbose)
            if verbose:
                typer.echo(f"    Pool has {available_count} stamps available for requested size/depth")

            if available_count == 0:
                typer.secho("ERROR: No stamps available in pool for requested size/depth.", fg=typer.colors.RED, err=True)
                typer.echo("Try again later, use a different size, or use regular purchase (without --usePool).")
                raise typer.Exit(code=1)

            # Acquire stamp from pool
            acquire_result = gw_client.acquire_stamp_from_pool(size=size, depth=stamp_depth, verbose=verbose)
            stamp_id = acquire_result.batch_id
            acquired_from_pool = True

            if verbose:
                typer.echo(f"    Stamp ID Received: {stamp_id} (Length: {len(stamp_id)})")
                typer.echo(f"    Depth: {acquire_result.depth}, Size: {acquire_result.size_name}")
                if acquire_result.fallback_used:
                    typer.secho(f"    Note: Larger stamp substituted (fallback used)", fg=typer.colors.YELLOW)
            else:
                msg = f"Stamp acquired from pool (ID: ...{stamp_id[-12:]})"
                if acquire_result.fallback_used:
                    msg += " [fallback size]"
                typer.echo(msg)

        except exceptions.PoolNotEnabledError:
            typer.secho("ERROR: Stamp pool is not enabled on this gateway.", fg=typer.colors.RED, err=True)
            typer.echo("Use regular purchase (without --usePool) instead.")
            raise typer.Exit(code=1)
        except exceptions.PoolEmptyError as e:
            typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
            typer.echo("Try again later, use a different size, or use regular purchase (without --usePool).")
            raise typer.Exit(code=1)
        except exceptions.PoolAcquisitionError as e:
            typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
            if e.available_count > 0:
                typer.echo(f"Pool shows {e.available_count} stamps available - this may be a race condition.")
                typer.echo("Try again immediately, or use regular purchase (without --usePool).")
            raise typer.Exit(code=1)
        except exceptions.PaymentRequiredError as e:
            typer.secho(f"\nERROR: Payment required but not completed.", fg=typer.colors.RED, err=True)
            typer.echo("Use --x402 to enable x402 payments, or use a gateway without x402 mode.")
            if hasattr(e, 'payment_options') and e.payment_options:
                typer.echo(f"Payment options: {e.payment_options}")
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"ERROR: Failed acquiring stamp from pool: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        # Purchase a new stamp
        typer.echo(f"Purchasing postage stamp...")
        if verbose:
            backend_url = gateway_url if use_gateway else local_bee_url
            if use_gateway:
                typer.echo(f"    (Duration: {duration or 'default'}h, Size: {size or 'default'}, Depth: {stamp_depth or 'default'} from {backend_url})")
            else:
                typer.echo(f"    (Amount: {stamp_amount or config.DEFAULT_POSTAGE_AMOUNT}, Depth: {stamp_depth or config.DEFAULT_POSTAGE_DEPTH} from {backend_url})")
        try:
            if use_gateway:
                gw_client = _get_gateway_client_with_x402(gateway_url, verbose)
                stamp_id = gw_client.purchase_stamp(
                    duration_hours=duration,
                    size=size,
                    depth=stamp_depth,
                    amount=stamp_amount,  # Legacy fallback
                    verbose=verbose
                )
            else:
                # Local backend still uses amount/depth
                local_amount = stamp_amount or config.DEFAULT_POSTAGE_AMOUNT
                local_depth = stamp_depth or config.DEFAULT_POSTAGE_DEPTH
                stamp_id = swarm_client.purchase_postage_stamp(local_bee_url, local_amount, local_depth, verbose=verbose)
            if verbose:
                typer.echo(f"    Stamp ID Received: {stamp_id} (Length: {len(stamp_id)})")
                typer.echo(f"    Stamp ID (lowercase for header): {stamp_id.lower()}")
            else:
                typer.echo(f"Postage stamp purchased (ID: ...{stamp_id[-12:]})")

        except exceptions.PaymentRequiredError as e:
            typer.secho(f"\nERROR: Payment required but not completed.", fg=typer.colors.RED, err=True)
            typer.echo("Use --x402 to enable x402 payments, or use a gateway without x402 mode.")
            if hasattr(e, 'payment_options') and e.payment_options:
                typer.echo(f"Payment options: {e.payment_options}")
            raise typer.Exit(code=1)
        except exceptions.StampPurchaseError as e:
            typer.secho(f"ERROR: Failed purchasing stamp: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"ERROR: Failed purchasing stamp: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    # Poll for stamp existence and usability
    if used_existing_stamp:
        typer.echo(f"Verifying stamp is usable...")
    elif acquired_from_pool:
        typer.echo(f"Verifying pooled stamp is usable...")
    else:
        typer.echo(f"Waiting for stamp to become usable (up to {stamp_check_retries * stamp_check_interval // 60} minutes)...")
    stamp_is_ready_for_upload = False
    for i in range(stamp_check_retries):
        if not verbose:
            # Simple progress indicator for non-verbose mode
            typer.echo(f"Checking stamp usability (attempt {i+1}/{stamp_check_retries})... ", nl=False)

        try:
            # Get stamp info using appropriate backend
            if use_gateway:
                gw_client = _get_gateway_client_with_x402(gateway_url, verbose)
                stamp_details = gw_client.get_stamp(stamp_id, verbose=verbose)
                if stamp_details:
                    stamp_info = {
                        "exists": stamp_details.exists,
                        "usable": stamp_details.usable,
                        "batchTTL": stamp_details.batchTTL,
                    }
                else:
                    stamp_info = None
            else:
                stamp_info = swarm_client.get_stamp_info(local_bee_url, stamp_id, verbose=verbose)

            if stamp_info:
                exists = stamp_info.get("exists")
                usable = stamp_info.get("usable", False)
                batch_ttl_seconds = stamp_info.get("batchTTL")  # TTL in seconds

                if verbose:
                    ttl_str = f"{batch_ttl_seconds // 60}m {batch_ttl_seconds % 60}s" if batch_ttl_seconds is not None else "N/A"
                    typer.echo(f"    Attempt {i+1}: Stamp found - Exists={exists}, Usable={usable}, TTL={ttl_str}")

                # Check usable flag - exists may be None from gateway API
                if usable:
                    stamp_is_ready_for_upload = True
                    if not verbose: typer.echo(typer.style("OK", fg=typer.colors.GREEN))
                    else: typer.secho(f"    Stamp {stamp_id.lower()} is now USABLE!", fg=typer.colors.GREEN)
                    break
                else:
                    if not verbose: typer.echo("retrying...")
            else:
                if not verbose: typer.echo("not found, retrying...")

        except Exception as e:
            if not verbose: typer.echo(typer.style("error checking, retrying...", fg=typer.colors.YELLOW))
            else: typer.echo(f"    Warning: Error during stamp info check on attempt {i+1}: {e}")


        if i < stamp_check_retries - 1:
            if verbose:
                typer.echo(f"    Waiting {stamp_check_interval}s before next check...")
            time.sleep(stamp_check_interval)
        elif not stamp_is_ready_for_upload and not verbose:  # Last attempt failed, print newline
            typer.echo(typer.style("failed.", fg=typer.colors.RED))


    if not stamp_is_ready_for_upload:
        typer.secho(f"ERROR: Stamp {stamp_id.lower()} did not become USABLE after {stamp_check_retries} retries.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # 7. (Final) Construct "Provenance Metadata" JSON object
    final_metadata_obj = metadata_builder.create_provenance_metadata_object(
            base64_data=b64_encoded_data, content_hash=sha256_hash, stamp_id=stamp_id,
            provenance_standard=provenance_standard, encryption=encryption )
    final_payload_bytes = metadata_builder.serialize_metadata_to_bytes(final_metadata_obj)
    if verbose:
        typer.echo(f"    Final Metadata Object created with stamp_id: {final_metadata_obj.stamp_id}")
        typer.echo(f"    Preview of final_payload_bytes (first 100): {final_payload_bytes[:100].decode('utf-8', errors='replace')}...")

    # 8 & 9. Upload "Provenance Metadata" JSON (with optional signing)
    if use_signing:
        typer.echo(f"Uploading data to Swarm with notary signature...")
    else:
        typer.echo(f"Uploading data to Swarm...")
    if verbose:
        typer.echo(f"    (Using stamp_id: {stamp_id.lower()} in header)")

    signed_document = None
    try:
        if use_gateway:
            gw_client = _get_gateway_client_with_x402(gateway_url, verbose)
            if use_signing:
                # Upload with notary signing
                result = gw_client.upload_data_with_signing(
                    final_payload_bytes, stamp_id, sign="notary", verbose=verbose
                )
                swarm_ref_hash = result.reference
                signed_document = result.signed_document
            else:
                swarm_ref_hash = gw_client.upload_data(final_payload_bytes, stamp_id, verbose=verbose)
        else:
            swarm_ref_hash = swarm_client.upload_data(local_bee_url, final_payload_bytes, stamp_id, verbose=verbose)
    except exceptions.NotaryNotEnabledError:
        typer.secho(f"\nERROR: Notary signing is not enabled on this gateway.", fg=typer.colors.RED, err=True)
        typer.echo("Remove --sign option or use a gateway with notary enabled.")
        raise typer.Exit(code=1)
    except exceptions.NotaryNotConfiguredError:
        typer.secho(f"\nERROR: Notary is enabled but not configured on this gateway.", fg=typer.colors.RED, err=True)
        typer.echo("Contact the gateway operator or remove --sign option.")
        raise typer.Exit(code=1)
    except exceptions.InvalidDocumentFormatError as e:
        typer.secho(f"\nERROR: Invalid document format for signing: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except exceptions.PaymentRequiredError as e:
        typer.secho(f"\nERROR: Payment required but not completed.", fg=typer.colors.RED, err=True)
        typer.echo("Use --x402 to enable x402 payments, or use a gateway without x402 mode.")
        if hasattr(e, 'payment_options') and e.payment_options:
            typer.echo(f"Payment options: {e.payment_options}")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"ERROR: Failed uploading data: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # 10. Display Swarm reference_hash
    typer.secho(f"\nSUCCESS! Upload complete.", fg=typer.colors.GREEN, bold=True)
    typer.echo("Swarm Reference Hash:")
    typer.secho(f"{swarm_ref_hash}", fg=typer.colors.CYAN)

    # Display signature info if signing was used
    if use_signing and signed_document:
        signatures = signed_document.get("signatures", [])
        notary_sig = None
        for sig in signatures:
            if sig.get("type") == "notary":
                notary_sig = sig
                break

        if notary_sig:
            typer.echo("\nSignature added:")
            signer = notary_sig.get("signer", "")
            signer_short = f"{signer[:10]}...{signer[-4:]}" if len(signer) > 14 else signer
            typer.echo(f"  Type:      {notary_sig.get('type', 'notary')}")
            typer.echo(f"  Signer:    {signer_short}")
            typer.echo(f"  Timestamp: {notary_sig.get('timestamp', 'N/A')}")
            if verbose:
                typer.echo(f"  Data hash: {notary_sig.get('data_hash', 'N/A')}")
                hashed_fields = notary_sig.get("hashed_fields")
                if hashed_fields:
                    typer.echo(f"  Hashed fields: {hashed_fields}")
                msg_format = notary_sig.get("signed_message_format")
                if msg_format:
                    typer.echo(f"  Message format: {msg_format}")
    elif use_signing:
        typer.secho("\nNote: Signature requested but signed document not returned by gateway.", fg=typer.colors.YELLOW)

@app.command()
def download(
    swarm_hash: Annotated[str, typer.Argument(help="Swarm reference hash of the Provenance Metadata to download.")],
    output_dir: Annotated[Path, typer.Option(
        "--output-dir", "-o",
        help="Directory to save the downloaded files.",
        file_okay=False,
        dir_okay=True,
        writable=True,
        resolve_path=True,
        default_factory=lambda: Path.cwd()  # Default to current working directory
    )],
    bee_url: Annotated[Optional[str], typer.Option("--bee-url", help="Bee Gateway URL (when backend=local).")] = None,
    verify: Annotated[bool, typer.Option("--verify", help="Verify notary signature if present (gateway only for address lookup).")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output for debugging.")] = False
):
    """
    Downloads Provenance Metadata from Swarm, decodes the wrapped data,
    verifies its integrity, and saves both files.

    Use --verify to verify notary signatures if present.
    """
    # Determine which backend to use
    use_gateway = _backend_config["backend"] == "gateway"
    gateway_url = _backend_config["gateway_url"]
    local_bee_url = bee_url or _backend_config["bee_url"]

    # Show warning for local backend
    if not use_gateway:
        _show_local_backend_warning()

    if verbose:
        typer.echo("Verbose mode enabled.")
        typer.echo(f"--> Initial Config for Download:")
        typer.echo(f"    Backend: {_backend_config['backend']}")
        typer.echo(f"    Swarm Hash: {swarm_hash}")
        typer.echo(f"    Output Directory: {output_dir}")
        if use_gateway:
            typer.echo(f"    Gateway URL: {gateway_url}")
        else:
            typer.echo(f"    Bee URL: {local_bee_url}")
    else:
        typer.echo(f"Downloading data for Swarm hash: {swarm_hash[:12]}...")

    # 1 & 2. Request and retrieve data (Provenance Metadata JSON bytes)
    backend_url = gateway_url if use_gateway else local_bee_url
    typer.echo(f"Fetching metadata from Swarm via {backend_url}...")
    try:
        if use_gateway:
            gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
            metadata_bytes = gw_client.download_data(swarm_hash, verbose=verbose)
        else:
            metadata_bytes = swarm_client.download_data_from_swarm(local_bee_url, swarm_hash, verbose=verbose)
        if verbose:
            typer.echo(f"    Successfully fetched {len(metadata_bytes)} bytes of metadata.")
    except FileNotFoundError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"ERROR: Failed fetching metadata from Swarm: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # 3. Deserialize fetched data to "Provenance Metadata" JSON object
    try:
        metadata_str = metadata_bytes.decode('utf-8')
        # provenance_metadata_obj = ProvenanceMetadata(**json.loads(metadata_str)) # Old Pydantic v1 way
        provenance_metadata_obj = ProvenanceMetadata.model_validate_json(metadata_str) # Pydantic v2 way
        if verbose:
            typer.echo("    Successfully parsed metadata JSON.")
            # typer.echo(f"    Parsed Metadata: {provenance_metadata_obj.model_dump(exclude={'data'})}") # Exclude large data field
    except (json.JSONDecodeError, ValidationError) as e: # Catch Pydantic validation errors too
        typer.secho(f"ERROR: Fetched data is not valid Provenance Metadata JSON: {e}", fg=typer.colors.RED, err=True)
        # Optionally save the invalid data for inspection
        try:
            invalid_data_path = output_dir / f"{swarm_hash}.invalid_metadata.txt"
            file_utils.save_bytes_to_file(invalid_data_path, metadata_bytes)
            typer.echo(f"    Saved invalid data to: {invalid_data_path}")
        except Exception as save_e:
            typer.echo(f"    Could not save invalid data: {save_e}")
        raise typer.Exit(code=1)
    except Exception as e: # Catch other unexpected errors
        typer.secho(f"ERROR: Unexpected error parsing metadata: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


    # 4. Validate expected JSON structure (Pydantic does this on parsing)
    #    and check for essential fields if not using Pydantic or for extra safety.
    #    Pydantic model already ensures 'data' and 'content_hash' exist if parsing succeeds.

    # 4.5 Verify notary signature if requested
    if verify:
        from .core.notary_utils import verify_notary_signature, has_notary_signature

        # Parse the raw metadata to check for signatures
        try:
            raw_document = json.loads(metadata_str)
        except json.JSONDecodeError:
            raw_document = {}

        if has_notary_signature(raw_document):
            typer.echo("\nSignature Verification:")
            typer.echo("-" * 50)

            # Get expected notary address from gateway
            expected_address = None
            if use_gateway:
                try:
                    gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
                    notary_info = gw_client.get_notary_info(verbose=verbose)
                    expected_address = notary_info.address
                    if verbose:
                        typer.echo(f"    Fetched notary address: {expected_address}")
                except exceptions.NotaryNotEnabledError:
                    typer.secho("  Warning: Could not fetch notary address (notary not enabled on gateway)", fg=typer.colors.YELLOW)
                except Exception as e:
                    typer.secho(f"  Warning: Could not fetch notary address: {e}", fg=typer.colors.YELLOW)

            if expected_address:
                # Extract signature info for display
                signatures = raw_document.get("signatures", [])
                notary_sig = None
                for sig in signatures:
                    if sig.get("type") == "notary":
                        notary_sig = sig
                        break

                if notary_sig:
                    signer = notary_sig.get("signer", "")
                    signer_short = f"{signer[:10]}...{signer[-4:]}" if len(signer) > 14 else signer
                    typer.echo(f"  Type:      {notary_sig.get('type', 'unknown')}")
                    typer.echo(f"  Signer:    {signer_short}")
                    typer.echo(f"  Timestamp: {notary_sig.get('timestamp', 'unknown')}")
                    if verbose:
                        hashed_fields = notary_sig.get("hashed_fields")
                        if hashed_fields:
                            typer.echo(f"  Hashed fields: {hashed_fields}")
                        msg_format = notary_sig.get("signed_message_format")
                        if msg_format:
                            typer.echo(f"  Message format: {msg_format}")

                # Verify signature
                is_valid, error_msg = verify_notary_signature(raw_document, expected_address)

                if is_valid:
                    typer.secho(f"  Signature: ✓ Verified", fg=typer.colors.GREEN)
                else:
                    typer.secho(f"  Signature: ✗ FAILED - {error_msg}", fg=typer.colors.RED)
            else:
                typer.secho("  Cannot verify: No notary address available", fg=typer.colors.YELLOW)
                typer.echo("  Use gateway backend or run 'notary verify' manually with --address")
        else:
            typer.echo("\nNo notary signatures found in document.")

    # 5. Extract Base64 encoded data
    b64_encoded_original_data = provenance_metadata_obj.data
    if verbose:
        typer.echo(f"    Extracted Base64 data (first 50 chars): {b64_encoded_original_data[:50]}...")

    # 6. Base64 decode
    try:
        raw_provenance_bytes = file_utils.base64_decode_data(b64_encoded_original_data)
        if verbose:
            typer.echo(f"    Successfully Base64 decoded {len(raw_provenance_bytes)} bytes of original data.")
    except ValueError as e:
        typer.secho(f"ERROR: Failed to Base64 decode data from metadata: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # 7. Calculate SHA256 hash of raw_provenance_bytes
    calculated_content_hash = file_utils.calculate_sha256(raw_provenance_bytes)
    if verbose:
        typer.echo(f"    Calculated SHA256 of decoded data: {calculated_content_hash}")

    # 8. Extract expected_hash
    expected_content_hash = provenance_metadata_obj.content_hash
    if verbose:
        typer.echo(f"    Expected SHA256 from metadata:    {expected_content_hash}")

    # Perform verification and save files
    output_dir.mkdir(parents=True, exist_ok=True) # Ensure output directory exists

    # 10. Save "Provenance Metadata" JSON
    metadata_filename = f"{swarm_hash}.meta.json"
    metadata_filepath = output_dir / metadata_filename
    try:
        # Save the pretty-printed JSON version of the Pydantic model
        file_utils.save_bytes_to_file(metadata_filepath, provenance_metadata_obj.model_dump_json(indent=2).encode('utf-8'))
        typer.echo(f"Provenance metadata saved to: {metadata_filepath}")
    except Exception as e:
        typer.secho(f"ERROR: Failed to save metadata file: {e}", fg=typer.colors.RED, err=True)
        # Continue to try and save data if verification passes, or decide to exit

    # 9. Verification
    if calculated_content_hash == expected_content_hash:
        typer.secho("SUCCESS: Content hash verification passed!", fg=typer.colors.GREEN)
        # 11. Save decoded raw_provenance_bytes
        data_filename = f"{swarm_hash}.data"
        data_filepath = output_dir / data_filename
        try:
            file_utils.save_bytes_to_file(data_filepath, raw_provenance_bytes)
            typer.echo(f"Decoded provenance data saved to: {data_filepath}")
            typer.secho(f"\nDownload and verification successful.", fg=typer.colors.GREEN, bold=True)
        except Exception as e:
            typer.secho(f"ERROR: Failed to save decoded data file: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        typer.secho("ERROR: Content hash verification FAILED!", fg=typer.colors.RED, bold=True)
        typer.echo(f"  Calculated hash: {calculated_content_hash}")
        typer.echo(f"  Expected hash:   {expected_content_hash}")
        # Optionally save the (unverified) decoded data with a warning filename
        unverified_data_filename = f"{swarm_hash}.UNVERIFIED.data"
        unverified_data_filepath = output_dir / unverified_data_filename
        try:
            file_utils.save_bytes_to_file(unverified_data_filepath, raw_provenance_bytes)
            typer.echo(f"Decoded (but UNVERIFIED) data saved to: {unverified_data_filepath}")
        except Exception as e:
            typer.echo(f"Could not save unverified data: {e}")
        raise typer.Exit(code=1)


@app.command("upload-collection")
def upload_collection(
    directory: Annotated[str, typer.Argument(help="Path to the directory to upload as a collection.")],
    provenance_standard: Annotated[Optional[str], typer.Option("--std", help="Identifier for the provenance standard used (optional).")] = None,
    duration: Annotated[Optional[int], typer.Option("--duration", "-d", help="Stamp validity in hours (min 24, gateway only).")] = None,
    size: Annotated[Optional[str], typer.Option("--size", help="Stamp size preset: 'small', 'medium', 'large' (gateway only).")] = None,
    stamp_id: Annotated[Optional[str], typer.Option("--stamp-id", "-s", help="Existing stamp ID to reuse (skips stamp purchase).")] = None,
    use_pool: Annotated[bool, typer.Option("--usePool", help="Acquire stamp from pool instead of purchasing (faster ~5s vs >1min).")] = False,
    deferred: Annotated[bool, typer.Option("--deferred", help="Use deferred upload mode.")] = False,
    redundancy: Annotated[bool, typer.Option("--redundancy", help="Enable redundancy for the upload.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output result as JSON.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output for debugging.")] = False,
):
    """Upload a directory as a Swarm manifest (collection).

    Creates a TAR archive from the directory and uploads it to the gateway
    as a Swarm manifest. Files are accessible via path-based URLs:
    bzz/<reference>/path/to/file

    Gateway only — local Bee backend is not supported for manifest uploads.
    """
    import tempfile

    # Gateway-only check
    if _backend_config["backend"] != "gateway":
        typer.secho(
            "ERROR: 'upload-collection' requires gateway backend. Use --backend gateway",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=1)

    # Validate directory
    dir_path = Path(directory).resolve()
    if not dir_path.is_dir():
        typer.secho(f"ERROR: Not a directory: {directory}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Check non-empty
    all_files = [f for f in dir_path.rglob("*") if f.is_file()]
    if not all_files:
        typer.secho(f"ERROR: Directory is empty: {directory}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]

    if verbose:
        typer.echo("Verbose mode enabled.")
        typer.echo(f"--> Collection Upload Config:")
        typer.echo(f"    Directory: {dir_path}")
        typer.echo(f"    Gateway URL: {gateway_url}")
        typer.echo(f"    File count: {len(all_files)}")
        if duration:
            typer.echo(f"    Duration: {duration} hours")
        if size:
            typer.echo(f"    Size: {size}")
        if deferred:
            typer.echo(f"    Deferred: Yes")
        if redundancy:
            typer.echo(f"    Redundancy: Yes")
    else:
        typer.echo(f"Processing directory: {dir_path.name}/ ({len(all_files)} files)...")

    # Scan directory: per-file hashes
    try:
        collection_hash, file_infos = file_utils.calculate_directory_hash_and_files(dir_path)
    except ValueError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    total_size = sum(f["size"] for f in file_infos)

    if verbose:
        typer.echo(f"    Collection hash: {collection_hash}")
        typer.echo(f"    Total size: {total_size} bytes")
        for fi in file_infos:
            typer.echo(f"    File: {fi['path']} ({fi['size']} bytes) hash={fi['content_hash'][:16]}...")

    # Create TAR in temp directory
    try:
        tmp_dir = tempfile.mkdtemp()
        tar_path = Path(tmp_dir) / "collection.tar"
        file_utils.create_tar_from_directory(dir_path, tar_path)
        tar_size = tar_path.stat().st_size
        if verbose:
            typer.echo(f"    TAR archive created: {tar_size} bytes")
    except (ValueError, OSError) as e:
        typer.secho(f"ERROR: Failed creating TAR archive: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Acquire stamp
    try:
        gw_client = _get_gateway_client_with_x402(gateway_url, verbose)

        if stamp_id:
            typer.echo(f"Using existing stamp: ...{stamp_id[-12:]}")
        elif use_pool:
            typer.echo("Acquiring stamp from pool...")
            acquire_result = gw_client.acquire_stamp_from_pool(size=size, verbose=verbose)
            stamp_id = acquire_result.batch_id
            if verbose:
                typer.echo(f"    Stamp ID: {stamp_id}")
            else:
                msg = f"Stamp acquired from pool (ID: ...{stamp_id[-12:]})"
                if acquire_result.fallback_used:
                    msg += " [fallback size]"
                typer.echo(msg)
        else:
            typer.echo("Purchasing postage stamp...")
            stamp_id = gw_client.purchase_stamp(
                duration_hours=duration,
                size=size,
                verbose=verbose,
            )
            if verbose:
                typer.echo(f"    Stamp ID: {stamp_id}")
            else:
                typer.echo(f"Postage stamp purchased (ID: ...{stamp_id[-12:]})")

    except exceptions.PoolNotEnabledError:
        typer.secho("ERROR: Stamp pool is not enabled on this gateway.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except exceptions.PaymentRequiredError as e:
        typer.secho(f"\nERROR: Payment required but not completed.", fg=typer.colors.RED, err=True)
        typer.echo("Use --x402 to enable x402 payments, or use a gateway without x402 mode.")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"ERROR: Failed acquiring stamp: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Upload manifest
    typer.echo("Uploading collection to Swarm...")
    try:
        result = gw_client.upload_manifest(
            tar_path=str(tar_path),
            stamp_id=stamp_id,
            deferred=deferred,
            include_timing=verbose,
            redundancy=redundancy,
            verbose=verbose,
        )
    except exceptions.PaymentRequiredError:
        typer.secho(f"\nERROR: Payment required but not completed.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"ERROR: Failed uploading collection: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    finally:
        # Cleanup temp TAR
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    # Output
    if output_json:
        from .models import CollectionFileInfo, CollectionProvenanceMetadata
        metadata = CollectionProvenanceMetadata(
            collection_hash=collection_hash,
            files=[CollectionFileInfo(**fi) for fi in file_infos],
            total_size=total_size,
            file_count=len(file_infos),
            stamp_id=stamp_id,
            swarm_reference=result.reference,
            provenance_standard=provenance_standard,
        )
        typer.echo(metadata.model_dump_json(indent=2))
    else:
        typer.secho(f"\nSUCCESS! Collection uploaded.", fg=typer.colors.GREEN, bold=True)
        typer.echo("Swarm Manifest Reference:")
        typer.secho(f"{result.reference}", fg=typer.colors.CYAN)
        typer.echo(f"\nFiles ({len(file_infos)}):")
        for fi in file_infos:
            typer.echo(f"  {fi['path']} ({fi['size']} bytes)")
        typer.echo(f"\nTotal size: {total_size} bytes")
        typer.echo(f"Collection hash: {collection_hash}")
        if provenance_standard:
            typer.echo(f"Provenance standard: {provenance_standard}")
        typer.echo(f"\nAccess files at:")
        bzz_base = f"bzz/{result.reference}"
        for fi in file_infos:
            typer.echo(f"  {bzz_base}/{fi['path']}")


# --- Stamps Subcommands ---

def _format_ttl(seconds: int) -> str:
    """Format TTL seconds into human readable string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    elif seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


@stamps_app.command("list")
def stamps_list(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    List all postage stamp batches. (Gateway only)
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'stamps list' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Listing stamps from {gateway_url}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        result = gw_client.list_stamps(verbose=verbose)

        if not result.stamps:
            typer.echo("No stamps found.")
            return

        # Print header
        typer.echo(f"\n{'ID':<20} {'Usable':<8} {'TTL':<12} {'Depth':<6} {'Utilization':<12}")
        typer.echo("-" * 60)

        for stamp in result.stamps:
            stamp_id_short = f"{stamp.batchID[:8]}...{stamp.batchID[-8:]}"
            usable_str = typer.style("Yes", fg=typer.colors.GREEN) if stamp.usable else typer.style("No", fg=typer.colors.RED)
            ttl_str = _format_ttl(stamp.batchTTL)
            util_str = f"{stamp.utilization}%"
            typer.echo(f"{stamp_id_short:<20} {usable_str:<8} {ttl_str:<12} {stamp.depth:<6} {util_str:<12}")

        typer.echo(f"\nTotal: {result.total_count} stamp(s)")

    except Exception as e:
        typer.secho(f"ERROR: Failed to list stamps: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@stamps_app.command("info")
def stamps_info(
    stamp_id: Annotated[str, typer.Argument(help="Stamp batch ID to get info for.")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Get detailed information about a specific stamp.
    """
    use_gateway = _backend_config["backend"] == "gateway"
    gateway_url = _backend_config["gateway_url"]
    bee_url = _backend_config["bee_url"]

    # Show warning for local backend
    if not use_gateway:
        _show_local_backend_warning()

    if verbose:
        backend_url = gateway_url if use_gateway else bee_url
        typer.echo(f"Getting stamp info from {backend_url}...")

    try:
        if use_gateway:
            gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
            stamp = gw_client.get_stamp(stamp_id, verbose=verbose)
            if not stamp:
                typer.secho(f"Stamp {stamp_id} not found.", fg=typer.colors.YELLOW)
                raise typer.Exit(code=1)

            typer.echo(f"\nStamp Details:")
            typer.echo(f"  Batch ID:    {stamp.batchID}")
            typer.echo(f"  Usable:      {typer.style('Yes', fg=typer.colors.GREEN) if stamp.usable else typer.style('No', fg=typer.colors.RED)}")
            typer.echo(f"  Exists:      {'Yes' if stamp.exists else 'No'}")
            typer.echo(f"  TTL:         {_format_ttl(stamp.batchTTL)}")
            typer.echo(f"  Depth:       {stamp.depth}")
            typer.echo(f"  Amount:      {stamp.amount}")
            typer.echo(f"  Utilization: {stamp.utilization}%")
            if stamp.label:
                typer.echo(f"  Label:       {stamp.label}")
        else:
            stamp_info = swarm_client.get_stamp_info(bee_url, stamp_id, verbose=verbose)
            if not stamp_info:
                typer.secho(f"Stamp {stamp_id} not found.", fg=typer.colors.YELLOW)
                raise typer.Exit(code=1)

            typer.echo(f"\nStamp Details:")
            typer.echo(f"  Batch ID:    {stamp_info.get('batchID', 'N/A')}")
            typer.echo(f"  Usable:      {'Yes' if stamp_info.get('usable') else 'No'}")
            typer.echo(f"  Exists:      {'Yes' if stamp_info.get('exists') else 'No'}")
            ttl = stamp_info.get('batchTTL')
            typer.echo(f"  TTL:         {_format_ttl(ttl) if ttl else 'N/A'}")
            typer.echo(f"  Depth:       {stamp_info.get('depth', 'N/A')}")
            typer.echo(f"  Amount:      {stamp_info.get('amount', 'N/A')}")

    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"ERROR: Failed to get stamp info: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@stamps_app.command("extend")
def stamps_extend(
    stamp_id: Annotated[str, typer.Argument(help="Stamp batch ID to extend.")],
    amount: Annotated[int, typer.Option("--amount", "-a", help="Amount of BZZ to add to the stamp.")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Extend an existing stamp by adding funds. (Gateway only)
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'stamps extend' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Extending stamp {stamp_id} with amount {amount}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        result_id = gw_client.extend_stamp(stamp_id, amount, verbose=verbose)
        typer.secho(f"SUCCESS: Stamp extended.", fg=typer.colors.GREEN)
        typer.echo(f"Batch ID: {result_id}")
    except Exception as e:
        typer.secho(f"ERROR: Failed to extend stamp: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@stamps_app.command("pool-status")
def stamps_pool_status(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Show stamp pool status and availability. (Gateway only)
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'stamps pool-status' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Getting pool status from {gateway_url}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        status = gw_client.get_pool_status(verbose=verbose)

        typer.echo(f"\nStamp Pool Status:")
        typer.echo("-" * 50)

        # Enabled status
        enabled_str = typer.style("Enabled", fg=typer.colors.GREEN) if status.enabled else typer.style("Disabled", fg=typer.colors.RED)
        typer.echo(f"  Status:       {enabled_str}")

        if not status.enabled:
            typer.echo("\nPool is not enabled on this gateway.")
            return

        # Total stamps
        typer.echo(f"  Total stamps: {status.total_stamps}")

        # Low reserve warning
        if status.low_reserve_warning:
            typer.secho(f"  Warning:      Pool is below target reserve levels", fg=typer.colors.YELLOW)

        # Available stamps by depth/size
        typer.echo(f"\n  Availability by size:")
        size_names = {"17": "small", "20": "medium", "22": "large"}
        for depth_str, count in status.current_levels.items():
            size_name = size_names.get(depth_str, f"depth-{depth_str}")
            target = status.reserve_config.get(depth_str, 0)
            available = len(status.available_stamps.get(depth_str, []))
            status_color = typer.colors.GREEN if available > 0 else typer.colors.RED
            typer.echo(f"    {size_name:<8} (depth {depth_str}): {typer.style(str(available), fg=status_color)} available / {count} total (target: {target})")

        # Maintenance info
        if status.last_check:
            typer.echo(f"\n  Last check:   {status.last_check}")
        if status.next_check:
            typer.echo(f"  Next check:   {status.next_check}")

        # Errors
        if status.errors:
            typer.echo(f"\n  Errors:")
            for error in status.errors:
                typer.secho(f"    - {error}", fg=typer.colors.RED)

    except exceptions.PoolNotEnabledError:
        typer.secho("Pool is not enabled on this gateway.", fg=typer.colors.YELLOW)
    except Exception as e:
        typer.secho(f"ERROR: Failed to get pool status: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@stamps_app.command("check")
def stamps_check(
    stamp_id: Annotated[str, typer.Argument(help="Stamp batch ID to check.")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Check if a stamp can be used for uploads. (Gateway only)

    Returns detailed health check including errors and warnings.
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'stamps check' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Checking stamp health from {gateway_url}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        health = gw_client.check_stamp_health(stamp_id, verbose=verbose)

        typer.echo(f"\nStamp Health Check:")
        typer.echo("-" * 50)
        typer.echo(f"  Stamp ID:   {health.stamp_id[:16]}...{health.stamp_id[-8:]}")

        # Can upload status
        if health.can_upload:
            typer.secho(f"  Can upload: Yes", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  Can upload: No", fg=typer.colors.RED)

        # Errors (blocking issues)
        if health.errors:
            typer.echo(f"\n  Errors (blocking):")
            for issue in health.errors:
                typer.secho(f"    [{issue.code}] {issue.message}", fg=typer.colors.RED)
                if issue.details and verbose:
                    for key, value in issue.details.items():
                        typer.echo(f"      {key}: {value}")

        # Warnings (non-blocking)
        if health.warnings:
            typer.echo(f"\n  Warnings:")
            for issue in health.warnings:
                typer.secho(f"    [{issue.code}] {issue.message}", fg=typer.colors.YELLOW)
                if issue.details and verbose:
                    for key, value in issue.details.items():
                        typer.echo(f"      {key}: {value}")

        # Detailed status (verbose only)
        if health.status and verbose:
            typer.echo(f"\n  Detailed status:")
            for key, value in health.status.items():
                typer.echo(f"    {key}: {value}")

        # Exit with error code if can't upload
        if not health.can_upload:
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"ERROR: Failed to check stamp health: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


# --- Info Commands ---

@app.command()
def wallet(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Show wallet address and BZZ balance. (Gateway only)
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'wallet' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Getting wallet info from {gateway_url}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        wallet_info = gw_client.get_wallet(verbose=verbose)
        typer.echo(f"\nWallet Information:")
        typer.echo(f"  Address: {wallet_info.walletAddress}")
        typer.echo(f"  BZZ Balance: {wallet_info.bzzBalance}")
    except Exception as e:
        typer.secho(f"ERROR: Failed to get wallet info: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def chequebook(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Show chequebook address and balance. (Gateway only)
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'chequebook' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Getting chequebook info from {gateway_url}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        cheque_info = gw_client.get_chequebook(verbose=verbose)
        typer.echo(f"\nChequebook Information:")
        typer.echo(f"  Address:           {cheque_info.chequebookAddress}")
        typer.echo(f"  Available Balance: {cheque_info.availableBalance}")
        typer.echo(f"  Total Balance:     {cheque_info.totalBalance}")
    except Exception as e:
        typer.secho(f"ERROR: Failed to get chequebook info: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def health(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Check if the backend is healthy and reachable.
    """
    import time as time_module

    use_gateway = _backend_config["backend"] == "gateway"
    gateway_url = _backend_config["gateway_url"]
    bee_url = _backend_config["bee_url"]
    backend_url = gateway_url if use_gateway else bee_url

    # Show warning for local backend
    if not use_gateway:
        _show_local_backend_warning()

    if verbose:
        typer.echo(f"Checking health of {backend_url}...")

    start_time = time_module.time()
    try:
        if use_gateway:
            gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
            is_healthy = gw_client.health_check(verbose=verbose)
        else:
            # For local Bee, try to get stamps endpoint as health check
            import requests
            response = requests.get(f"{bee_url}/health", timeout=10)
            is_healthy = response.status_code == 200

        elapsed_ms = int((time_module.time() - start_time) * 1000)

        if is_healthy:
            typer.secho(f"✓ Backend: {backend_url}", fg=typer.colors.GREEN)
            typer.secho(f"✓ Status: Healthy", fg=typer.colors.GREEN)
            typer.echo(f"  Response time: {elapsed_ms}ms")
        else:
            typer.secho(f"✗ Backend: {backend_url}", fg=typer.colors.RED)
            typer.secho(f"✗ Status: Unhealthy", fg=typer.colors.RED)
            raise typer.Exit(code=1)

    except Exception as e:
        typer.secho(f"✗ Backend: {backend_url}", fg=typer.colors.RED)
        typer.secho(f"✗ Status: Unreachable", fg=typer.colors.RED)
        if verbose:
            typer.echo(f"  Error: {e}")
        raise typer.Exit(code=1)


# --- x402 Subcommands ---

@x402_app.command("status")
def x402_status(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Show x402 payment configuration status.
    """
    import os

    typer.echo("\nx402 Payment Configuration:")
    typer.echo("-" * 40)

    # Enabled status
    enabled = _x402_config["enabled"]
    enabled_str = typer.style("Enabled", fg=typer.colors.GREEN) if enabled else typer.style("Disabled", fg=typer.colors.YELLOW)
    typer.echo(f"  Status:       {enabled_str}")

    # Network
    network = _x402_config["network"]
    network_color = typer.colors.CYAN if network == "base-sepolia" else typer.colors.MAGENTA
    typer.echo(f"  Network:      {typer.style(network, fg=network_color)}")

    # Auto-pay settings
    auto_pay = _x402_config["auto_pay"]
    max_pay = _x402_config["max_auto_pay_usd"]
    auto_str = typer.style("Yes", fg=typer.colors.GREEN) if auto_pay else typer.style("No", fg=typer.colors.YELLOW)
    typer.echo(f"  Auto-pay:     {auto_str}")
    typer.echo(f"  Max auto-pay: ${max_pay:.2f}")

    # Check for private key (don't show the actual key)
    pk_env_name = config.X402_PRIVATE_KEY_ENV
    has_pk = bool(os.getenv(pk_env_name) or os.getenv("X402_PRIVATE_KEY"))
    pk_str = typer.style("Configured", fg=typer.colors.GREEN) if has_pk else typer.style("Not set", fg=typer.colors.RED)
    typer.echo(f"  Private key:  {pk_str}")

    if has_pk and verbose:
        # Show wallet address (safe to display)
        try:
            from .core.x402_client import X402Client
            client = X402Client(network=network)
            typer.echo(f"  Wallet:       {client.wallet_address}")
        except Exception as e:
            typer.echo(f"  Wallet:       {typer.style(f'Error: {e}', fg=typer.colors.RED)}")

    typer.echo("")

    if not has_pk:
        typer.echo("To enable x402 payments, set your private key:")
        typer.echo(f"  export {pk_env_name}=0x...")
        typer.echo("")


@x402_app.command("balance")
def x402_balance(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Show USDC balance for the x402 wallet.
    """
    import os

    # Check for private key
    pk_env_name = config.X402_PRIVATE_KEY_ENV
    has_pk = bool(os.getenv(pk_env_name) or os.getenv("X402_PRIVATE_KEY"))

    if not has_pk:
        typer.secho(f"ERROR: No private key configured.", fg=typer.colors.RED, err=True)
        typer.echo(f"Set your private key: export {pk_env_name}=0x...")
        raise typer.Exit(code=1)

    network = _x402_config["network"]

    try:
        from .core.x402_client import X402Client
        client = X402Client(network=network)

        if verbose:
            typer.echo(f"Checking balance on {network}...")

        raw_balance, usdc_balance = client.get_usdc_balance()

        typer.echo(f"\nx402 Wallet Balance:")
        typer.echo("-" * 40)
        typer.echo(f"  Network: {network}")
        typer.echo(f"  Address: {client.wallet_address}")
        typer.echo(f"  USDC:    {typer.style(f'${usdc_balance:.6f}', fg=typer.colors.GREEN, bold=True)}")

        if network == "base-sepolia":
            typer.echo("")
            typer.echo("Get testnet USDC: https://faucet.circle.com/")

    except Exception as e:
        typer.secho(f"ERROR: Failed to get balance: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@x402_app.command("info")
def x402_info():
    """
    Show x402 setup instructions and useful links.
    """
    typer.echo("\nx402 Payment Setup Guide")
    typer.echo("=" * 50)

    typer.echo("\n1. Get a wallet private key:")
    typer.echo("   - Create new: Use MetaMask or any Ethereum wallet")
    typer.echo("   - Export private key (starts with 0x)")

    typer.echo("\n2. Set environment variable:")
    typer.echo("   export X402_PRIVATE_KEY=0x...")

    typer.echo("\n3. Get testnet funds (for testing):")
    typer.echo("   - ETH (gas): https://www.alchemy.com/faucets/base-sepolia")
    typer.echo("   - USDC:      https://faucet.circle.com/")

    typer.echo("\n4. Enable x402 when uploading:")
    typer.echo("   swarm-prov-upload --x402 upload --file data.txt")

    typer.echo("\n5. For auto-pay (up to $1 without prompting):")
    typer.echo("   swarm-prov-upload --x402 --auto-pay upload --file data.txt")

    typer.echo("\nConfiguration options (.env or environment):")
    typer.echo("   X402_ENABLED=true          # Enable by default")
    typer.echo("   X402_NETWORK=base-sepolia  # or 'base' for mainnet")
    typer.echo("   X402_AUTO_PAY=false        # Auto-pay without prompts")
    typer.echo("   X402_MAX_AUTO_PAY_USD=1.00 # Max auto-pay per request")

    typer.echo("\nUseful commands:")
    typer.echo("   swarm-prov-upload x402 status   # Check configuration")
    typer.echo("   swarm-prov-upload x402 balance  # Check USDC balance")
    typer.echo("")


# --- Notary Subcommands ---

@notary_app.command("info")
def notary_info(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Get notary service status and signer address. (Gateway only)
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'notary info' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Getting notary info from {gateway_url}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        info = gw_client.get_notary_info(verbose=verbose)

        typer.echo(f"\nNotary Service:")
        typer.echo("-" * 40)

        # Enabled status
        enabled_str = typer.style("Yes", fg=typer.colors.GREEN) if info.enabled else typer.style("No", fg=typer.colors.RED)
        typer.echo(f"  Enabled:   {enabled_str}")

        # Available status
        available_str = typer.style("Yes", fg=typer.colors.GREEN) if info.available else typer.style("No", fg=typer.colors.YELLOW)
        typer.echo(f"  Available: {available_str}")

        # Address
        if info.address:
            typer.echo(f"  Address:   {info.address}")
        else:
            typer.echo(f"  Address:   {typer.style('Not configured', fg=typer.colors.YELLOW)}")

        # Message
        if info.message:
            typer.echo(f"  Message:   {info.message}")

        typer.echo("")

    except exceptions.NotaryNotEnabledError:
        typer.secho("Notary signing is not enabled on this gateway.", fg=typer.colors.YELLOW)
    except Exception as e:
        typer.secho(f"ERROR: Failed to get notary info: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@notary_app.command("status")
def notary_status(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Quick health check for notary service. (Gateway only)
    """
    if _backend_config["backend"] != "gateway":
        typer.secho("ERROR: 'notary status' requires gateway backend. Use --backend gateway", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    gateway_url = _backend_config["gateway_url"]
    if verbose:
        typer.echo(f"Checking notary status from {gateway_url}...")

    try:
        gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
        status = gw_client.get_notary_status(verbose=verbose)

        if status.available:
            typer.secho(f"✓ Notary service: Available", fg=typer.colors.GREEN)
            if status.address:
                addr_short = f"{status.address[:10]}...{status.address[-4:]}"
                typer.echo(f"  Address: {addr_short}")
        else:
            typer.secho(f"✗ Notary service: Not available", fg=typer.colors.RED)
            if not status.enabled:
                typer.echo("  Reason: Not enabled on this gateway")
            else:
                typer.echo("  Reason: Enabled but not configured")
            raise typer.Exit(code=1)

    except exceptions.NotaryNotEnabledError:
        typer.secho(f"✗ Notary service: Not enabled", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"✗ Notary service: Error - {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@notary_app.command("verify")
def notary_verify(
    file: Annotated[Path, typer.Option(
        "--file", "-f",
        help="Path to the signed JSON document to verify.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    )],
    address: Annotated[Optional[str], typer.Option(
        "--address", "-a",
        help="Expected signer address (fetched from gateway if not provided)."
    )] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False
):
    """
    Verify a notary signature on a local JSON file. (Gateway only for address lookup)
    """
    from .core.notary_utils import verify_notary_signature, extract_notary_signature

    # Read and parse the file
    try:
        content = file.read_text(encoding="utf-8")
        document = json.loads(content)
    except json.JSONDecodeError as e:
        typer.secho(f"ERROR: File is not valid JSON: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"ERROR: Failed to read file: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Check if document has a notary signature
    notary_sig = extract_notary_signature(document)
    if not notary_sig:
        typer.secho("No notary signature found in document.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)

    # Get expected address
    expected_address = address
    if not expected_address:
        if _backend_config["backend"] != "gateway":
            typer.secho("ERROR: No --address provided and gateway backend not configured.", fg=typer.colors.RED, err=True)
            typer.echo("Provide --address or use --backend gateway to fetch address from gateway.")
            raise typer.Exit(code=1)

        gateway_url = _backend_config["gateway_url"]
        if verbose:
            typer.echo(f"Fetching notary address from {gateway_url}...")

        try:
            gw_client = GatewayClient(base_url=gateway_url, free_tier=_backend_config["free_tier"])
            info = gw_client.get_notary_info(verbose=verbose)
            expected_address = info.address
            if not expected_address:
                typer.secho("ERROR: Gateway notary has no address configured.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
        except exceptions.NotaryNotEnabledError:
            typer.secho("ERROR: Notary not enabled on gateway. Provide --address manually.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"ERROR: Failed to get notary address: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    # Display signature info
    typer.echo(f"\nSignature Verification:")
    typer.echo("-" * 50)
    typer.echo(f"  Type:      {notary_sig.get('type', 'unknown')}")

    signer = notary_sig.get("signer", "")
    signer_short = f"{signer[:10]}...{signer[-4:]}" if len(signer) > 14 else signer
    typer.echo(f"  Signer:    {signer_short}")
    typer.echo(f"  Timestamp: {notary_sig.get('timestamp', 'unknown')}")

    if verbose:
        typer.echo(f"  Data hash: {notary_sig.get('data_hash', 'unknown')}")
        sig_value = notary_sig.get("signature", "")
        sig_short = f"{sig_value[:20]}...{sig_value[-8:]}" if len(sig_value) > 28 else sig_value
        typer.echo(f"  Signature: {sig_short}")
        hashed_fields = notary_sig.get("hashed_fields")
        if hashed_fields:
            typer.echo(f"  Hashed fields: {hashed_fields}")
        msg_format = notary_sig.get("signed_message_format")
        if msg_format:
            typer.echo(f"  Message format: {msg_format}")

    # Verify
    is_valid, error_msg = verify_notary_signature(document, expected_address)

    if is_valid:
        typer.secho(f"\n  Result:    ✓ VERIFIED", fg=typer.colors.GREEN, bold=True)
        if signer.lower() == expected_address.lower():
            typer.echo(f"             Signer matches gateway notary")
    else:
        typer.secho(f"\n  Result:    ✗ FAILED", fg=typer.colors.RED, bold=True)
        typer.echo(f"             {error_msg}")
        raise typer.Exit(code=1)


# --- Chain Subcommands ---

@chain_app.command("balance")
def chain_balance(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Show wallet balance and chain configuration.
    """
    try:
        client = _get_chain_client(verbose=verbose)
        result = client.balance(verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output_json:
        typer.echo(json.dumps(result.model_dump(), indent=2))
        return

    typer.echo(f"\nChain Wallet:")
    typer.echo("-" * 40)
    typer.echo(f"  Address:  {result.address}")
    typer.echo(f"  Balance:  {result.balance_eth} ETH")
    typer.echo(f"  Chain:    {result.chain}")
    typer.echo(f"  Contract: {result.contract_address}")

    if result.chain == "base-sepolia":
        typer.echo("")
        typer.echo("Get testnet ETH: https://www.alchemy.com/faucets/base-sepolia")


@chain_app.command("verify")
def chain_verify(
    swarm_hash: Annotated[str, typer.Argument(help="Swarm reference hash to verify on-chain.")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
):
    """
    Verify that a Swarm hash is anchored on-chain.

    Exit code 0 if anchored, 1 if not found (useful for scripting).
    """
    try:
        client = _get_chain_client(verbose=verbose)
        is_registered = client.verify(swarm_hash, verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if is_registered:
        typer.secho(f"Verified: {swarm_hash} is anchored on-chain.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"Not found: {swarm_hash} is not registered on-chain.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)


@chain_app.command("get")
def chain_get(
    swarm_hash: Annotated[str, typer.Argument(help="Swarm reference hash to look up.")],
    follow: Annotated[bool, typer.Option("--follow", help="Walk the transformation chain.")] = False,
    depth: Annotated[Optional[int], typer.Option("--depth", help="Max chain depth when using --follow.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Get the on-chain provenance record for a Swarm hash.

    Use --follow to walk the full transformation chain.
    Use --depth to limit traversal depth.
    """
    if depth is not None and not follow:
        typer.secho("WARNING: --depth has no effect without --follow.", fg=typer.colors.YELLOW, err=True)

    if follow:
        # Chain walking mode
        try:
            client = _get_chain_client(verbose=verbose)
            chain_records = client.get_provenance_chain(swarm_hash, max_depth=depth, verbose=verbose)
        except typer.Exit:
            raise
        except exceptions.ChainConnectionError as e:
            typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
            if e.rpc_url:
                typer.echo(f"  RPC URL: {e.rpc_url}")
            raise typer.Exit(code=1)
        except exceptions.ChainError as e:
            typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        if not chain_records:
            typer.secho(f"Not found: {swarm_hash} is not registered on-chain.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)

        if output_json:
            output = {
                "chain": [r.model_dump() for r in chain_records],
                "depth": len(chain_records),
                "root": swarm_hash,
            }
            typer.echo(json.dumps(output, indent=2))
            return

        typer.echo(f"\nProvenance Chain ({len(chain_records)} records):")
        typer.echo("\u2550" * 35)

        for i, record in enumerate(chain_records, 1):
            hash_short = f"{record.data_hash[:12]}...{record.data_hash[-8:]}" if len(record.data_hash) > 20 else record.data_hash
            owner_short = f"{record.owner[:10]}...{record.owner[-4:]}" if len(record.owner) > 14 else record.owner

            label = "Original" if i == 1 else "Derived"
            typer.echo(f"\n\u250c\u2500\u2500\u2500 [{i}] {label} \u2500\u2500\u2500")
            typer.echo(f"\u2502  Hash:   {hash_short}")
            typer.echo(f"\u2502  Type:   {record.data_type}")
            typer.echo(f"\u2502  Owner:  {owner_short}")
            typer.echo(f"\u2502  Status: {record.status.name}")

            if record.transformations:
                for t in record.transformations:
                    typer.echo(f"\u2502")
                    desc = t.description if t.description else "transformation"
                    typer.echo(f"\u2514\u2500\u2500\u2500\u2500 -> [{desc}] \u2500\u2500\u2500\u2500")
            else:
                typer.echo(f"\u2502")
                typer.echo(f"\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

        return

    # Single record mode
    try:
        client = _get_chain_client(verbose=verbose)
        record = client.get(swarm_hash, verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.DataNotRegisteredError:
        typer.secho(f"Not found: {swarm_hash} is not registered on-chain.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output_json:
        typer.echo(json.dumps(record.model_dump(), indent=2))
        return

    from datetime import datetime, timezone
    ts_str = datetime.fromtimestamp(record.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    hash_short = f"{record.data_hash[:12]}...{record.data_hash[-8:]}" if len(record.data_hash) > 20 else record.data_hash
    owner_short = f"{record.owner[:10]}...{record.owner[-4:]}" if len(record.owner) > 14 else record.owner

    typer.echo(f"\nProvenance Record:")
    typer.echo("-" * 50)
    typer.echo(f"  Hash:    {hash_short}")
    typer.echo(f"  Owner:   {owner_short}")
    typer.echo(f"  Type:    {record.data_type}")
    typer.echo(f"  Status:  {record.status.name}")
    typer.echo(f"  Time:    {ts_str}")

    if record.transformations:
        typer.echo(f"\n  Transformations ({len(record.transformations)}):")
        for t in record.transformations:
            if t.new_data_hash:
                t_hash = f"{t.new_data_hash[:12]}..." if len(t.new_data_hash) > 12 else t.new_data_hash
                typer.echo(f"    -> {t_hash}: {t.description}")
            else:
                typer.echo(f"    - {t.description}")

    if record.accessors:
        typer.echo(f"\n  Accessors ({len(record.accessors)}):")
        for addr in record.accessors:
            addr_short = f"{addr[:10]}...{addr[-4:]}" if len(addr) > 14 else addr
            typer.echo(f"    - {addr_short}")


@chain_app.command("anchor")
def chain_anchor(
    swarm_hash: Annotated[str, typer.Argument(help="Swarm reference hash to anchor on-chain.")],
    data_type: Annotated[str, typer.Option("--type", "-t", help="Data type/category.")] = "swarm-provenance",
    owner: Annotated[Optional[str], typer.Option("--owner", help="Register on behalf of this owner address (requires delegate authorization).")] = None,
    gas: Annotated[Optional[int], typer.Option("--gas", help="Explicit gas limit (skips estimation).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Anchor a Swarm hash on-chain by registering it in the DataProvenance contract.

    Use --owner to register on behalf of another address (caller must be authorized delegate).
    """
    if gas is not None:
        _chain_config["gas_limit"] = gas
    try:
        client = _get_chain_client(verbose=verbose)
        if owner:
            result = client.anchor_for(swarm_hash, owner=owner, data_type=data_type, verbose=verbose)
        else:
            result = client.anchor(swarm_hash, data_type=data_type, verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.DataAlreadyRegisteredError as e:
        if output_json:
            from datetime import datetime, timezone
            typer.echo(json.dumps({
                "error": "already_registered",
                "data_hash": e.data_hash,
                "owner": e.owner,
                "timestamp": e.timestamp,
                "data_type": e.data_type,
            }, indent=2))
        else:
            from datetime import datetime, timezone
            ts_str = datetime.fromtimestamp(e.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if e.timestamp else "unknown"
            typer.secho(f"\nAlready registered: {e.data_hash}", fg=typer.colors.YELLOW)
            typer.echo(f"  Owner:   {e.owner}")
            typer.echo(f"  Type:    {e.data_type}")
            typer.echo(f"  Time:    {ts_str}")
        raise typer.Exit(code=1)
    except exceptions.ChainTransactionError as e:
        typer.secho(f"ERROR: Transaction failed: {e}", fg=typer.colors.RED, err=True)
        if e.tx_hash:
            typer.echo(f"  Transaction: {e.tx_hash}")
        raise typer.Exit(code=1)
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output_json:
        typer.echo(json.dumps(result.model_dump(), indent=2))
        return

    typer.secho(f"\nAnchored successfully!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Hash:    {swarm_hash}")
    typer.echo(f"  Type:    {data_type}")
    if owner:
        typer.echo(f"  Owner:   {owner}")
    typer.echo(f"  Tx:      {result.tx_hash}")
    typer.echo(f"  Block:   {result.block_number}")
    typer.echo(f"  Gas:     {result.gas_used}")
    if result.explorer_url:
        typer.echo(f"  Explorer: {result.explorer_url}")


@chain_app.command("access")
def chain_access(
    swarm_hash: Annotated[str, typer.Argument(help="Swarm reference hash to record access for.")],
    gas: Annotated[Optional[int], typer.Option("--gas", help="Explicit gas limit (skips estimation).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Record that data was accessed on-chain.

    This operation is idempotent - recording access multiple times
    for the same hash and accessor is safe.
    """
    if gas is not None:
        _chain_config["gas_limit"] = gas
    try:
        client = _get_chain_client(verbose=verbose)
        result = client.access(swarm_hash, verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.ChainTransactionError as e:
        typer.secho(f"ERROR: Transaction failed: {e}", fg=typer.colors.RED, err=True)
        if e.tx_hash:
            typer.echo(f"  Transaction: {e.tx_hash}")
        raise typer.Exit(code=1)
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output_json:
        typer.echo(json.dumps(result.model_dump(), indent=2))
        return

    typer.secho(f"\nAccess recorded!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Hash:    {swarm_hash}")
    typer.echo(f"  Tx:      {result.tx_hash}")
    typer.echo(f"  Block:   {result.block_number}")
    typer.echo(f"  Gas:     {result.gas_used}")
    if result.explorer_url:
        typer.echo(f"  Explorer: {result.explorer_url}")


@chain_app.command("status")
def chain_status(
    swarm_hash: Annotated[str, typer.Argument(help="Swarm reference hash to query or update status.")],
    set_status: Annotated[Optional[str], typer.Option("--set", help="Set status: active, restricted, deleted.")] = None,
    gas: Annotated[Optional[int], typer.Option("--gas", help="Explicit gas limit (skips estimation).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Query or set the on-chain status of a data hash.

    Without --set: shows current status.
    With --set: changes status to active, restricted, or deleted.
    """
    if gas is not None:
        _chain_config["gas_limit"] = gas
    status_map = {"active": 0, "restricted": 1, "deleted": 2}

    if set_status is not None:
        # Set status mode
        status_name = set_status.lower()
        if status_name not in status_map:
            typer.secho(
                f"ERROR: Invalid status '{set_status}'. Use: active, restricted, deleted.",
                fg=typer.colors.RED, err=True,
            )
            raise typer.Exit(code=1)

        try:
            client = _get_chain_client(verbose=verbose)
            result = client.set_status(swarm_hash, status=status_map[status_name], verbose=verbose)
        except typer.Exit:
            raise
        except exceptions.DataNotRegisteredError:
            typer.secho(f"ERROR: {swarm_hash} is not registered on-chain.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except exceptions.ChainTransactionError as e:
            typer.secho(f"ERROR: Transaction failed: {e}", fg=typer.colors.RED, err=True)
            if e.tx_hash:
                typer.echo(f"  Transaction: {e.tx_hash}")
            raise typer.Exit(code=1)
        except exceptions.ChainConnectionError as e:
            typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
            if e.rpc_url:
                typer.echo(f"  RPC URL: {e.rpc_url}")
            raise typer.Exit(code=1)
        except exceptions.ChainError as e:
            typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        if output_json:
            typer.echo(json.dumps(result.model_dump(), indent=2))
            return

        typer.secho(f"\nStatus updated!", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"  Hash:    {swarm_hash}")
        typer.echo(f"  Status:  {status_name.upper()}")
        typer.echo(f"  Tx:      {result.tx_hash}")
        typer.echo(f"  Block:   {result.block_number}")
        typer.echo(f"  Gas:     {result.gas_used}")
        if result.explorer_url:
            typer.echo(f"  Explorer: {result.explorer_url}")
    else:
        # Query status mode
        try:
            client = _get_chain_client(verbose=verbose)
            record = client.get(swarm_hash, verbose=verbose)
        except typer.Exit:
            raise
        except exceptions.DataNotRegisteredError:
            typer.secho(f"Not found: {swarm_hash} is not registered on-chain.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)
        except exceptions.ChainConnectionError as e:
            typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
            if e.rpc_url:
                typer.echo(f"  RPC URL: {e.rpc_url}")
            raise typer.Exit(code=1)
        except exceptions.ChainError as e:
            typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        if output_json:
            typer.echo(json.dumps({"hash": swarm_hash, "status": record.status.name}, indent=2))
            return

        hash_short = f"{swarm_hash[:12]}...{swarm_hash[-8:]}" if len(swarm_hash) > 20 else swarm_hash
        typer.echo(f"\nStatus: {hash_short}")
        typer.echo(f"  Status: {record.status.name}")


@chain_app.command("transfer")
def chain_transfer(
    swarm_hash: Annotated[str, typer.Argument(help="Swarm reference hash to transfer.")],
    to: Annotated[str, typer.Option("--to", help="New owner address.")],
    gas: Annotated[Optional[int], typer.Option("--gas", help="Explicit gas limit (skips estimation).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Transfer ownership of a data hash to a new address.
    """
    if gas is not None:
        _chain_config["gas_limit"] = gas
    try:
        client = _get_chain_client(verbose=verbose)
        result = client.transfer_ownership(swarm_hash, new_owner=to, verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.ChainTransactionError as e:
        typer.secho(f"ERROR: Transaction failed: {e}", fg=typer.colors.RED, err=True)
        if e.tx_hash:
            typer.echo(f"  Transaction: {e.tx_hash}")
        raise typer.Exit(code=1)
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output_json:
        typer.echo(json.dumps(result.model_dump(), indent=2))
        return

    to_short = f"{to[:10]}...{to[-4:]}" if len(to) > 14 else to
    typer.secho(f"\nOwnership transferred!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Hash:    {swarm_hash}")
    typer.echo(f"  New owner: {to_short}")
    typer.echo(f"  Tx:      {result.tx_hash}")
    typer.echo(f"  Block:   {result.block_number}")
    typer.echo(f"  Gas:     {result.gas_used}")
    if result.explorer_url:
        typer.echo(f"  Explorer: {result.explorer_url}")


@chain_app.command("delegate")
def chain_delegate(
    address: Annotated[str, typer.Argument(help="Delegate address to authorize or revoke.")],
    authorize: Annotated[bool, typer.Option("--authorize", help="Authorize this delegate.")] = False,
    revoke: Annotated[bool, typer.Option("--revoke", help="Revoke this delegate.")] = False,
    gas: Annotated[Optional[int], typer.Option("--gas", help="Explicit gas limit (skips estimation).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Authorize or revoke a delegate address.

    A delegate can anchor data on behalf of the caller.
    Must provide exactly one of --authorize or --revoke.
    """
    if gas is not None:
        _chain_config["gas_limit"] = gas
    if authorize == revoke:
        typer.secho(
            "ERROR: Specify exactly one of --authorize or --revoke.",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=1)

    try:
        client = _get_chain_client(verbose=verbose)
        result = client.set_delegate(delegate=address, authorized=authorize, verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.ChainTransactionError as e:
        typer.secho(f"ERROR: Transaction failed: {e}", fg=typer.colors.RED, err=True)
        if e.tx_hash:
            typer.echo(f"  Transaction: {e.tx_hash}")
        raise typer.Exit(code=1)
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output_json:
        typer.echo(json.dumps(result.model_dump(), indent=2))
        return

    action = "authorized" if authorize else "revoked"
    addr_short = f"{address[:10]}...{address[-4:]}" if len(address) > 14 else address
    typer.secho(f"\nDelegate {action}!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Address: {addr_short}")
    typer.echo(f"  Tx:      {result.tx_hash}")
    typer.echo(f"  Block:   {result.block_number}")
    typer.echo(f"  Gas:     {result.gas_used}")
    if result.explorer_url:
        typer.echo(f"  Explorer: {result.explorer_url}")


@chain_app.command("transform")
def chain_transform(
    original_hash: Annotated[str, typer.Argument(help="Hash of the original data.")],
    new_hash: Annotated[str, typer.Argument(help="Hash of the transformed data.")],
    description: Annotated[str, typer.Option("--description", "-d", help="Description of the transformation.")] = "",
    restrict_original: Annotated[bool, typer.Option("--restrict-original", help="Set original hash status to RESTRICTED after transform.")] = False,
    gas: Annotated[Optional[int], typer.Option("--gas", help="Explicit gas limit (skips estimation).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Record a data transformation on-chain, linking original to new hash.

    The original hash must already be anchored on-chain.
    Use --restrict-original to automatically restrict the original after transform.
    """
    if gas is not None:
        _chain_config["gas_limit"] = gas
    try:
        client = _get_chain_client(verbose=verbose)
        result = client.transform(original_hash, new_hash, description=description, verbose=verbose)
    except typer.Exit:
        raise
    except exceptions.DataNotRegisteredError as e:
        typer.secho(f"ERROR: Original hash is not registered on-chain.", fg=typer.colors.RED, err=True)
        typer.echo(f"  Anchor it first: swarm-prov-upload chain anchor {e.data_hash or original_hash}")
        raise typer.Exit(code=1)
    except exceptions.ChainTransactionError as e:
        typer.secho(f"ERROR: Transaction failed: {e}", fg=typer.colors.RED, err=True)
        if e.tx_hash:
            typer.echo(f"  Transaction: {e.tx_hash}")
        raise typer.Exit(code=1)
    except exceptions.ChainConnectionError as e:
        typer.secho(f"ERROR: Cannot connect to chain: {e}", fg=typer.colors.RED, err=True)
        if e.rpc_url:
            typer.echo(f"  RPC URL: {e.rpc_url}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Optionally restrict original
    status_result = None
    if restrict_original:
        try:
            status_result = client.set_status(original_hash, status=1, verbose=verbose)
        except exceptions.ChainError as e:
            typer.secho(f"\nWARNING: Transform succeeded but failed to restrict original: {e}", fg=typer.colors.YELLOW, err=True)

    if output_json:
        if restrict_original:
            combined = {
                "transform": result.model_dump(),
                "restrict": status_result.model_dump() if status_result else None,
            }
            typer.echo(json.dumps(combined, indent=2))
        else:
            typer.echo(json.dumps(result.model_dump(), indent=2))
        return

    typer.secho(f"\nTransformation recorded!", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Original: {original_hash}")
    typer.echo(f"  New:      {new_hash}")
    if description:
        typer.echo(f"  Desc:     {description}")
    typer.echo(f"  Tx:       {result.tx_hash}")
    typer.echo(f"  Block:    {result.block_number}")
    typer.echo(f"  Gas:      {result.gas_used}")
    if result.explorer_url:
        typer.echo(f"  Explorer: {result.explorer_url}")

    if status_result:
        typer.secho(f"\nOriginal hash restricted!", fg=typer.colors.GREEN)
        typer.echo(f"  Hash:    {original_hash}")
        typer.echo(f"  Status:  RESTRICTED")
        typer.echo(f"  Tx:      {status_result.tx_hash}")


@chain_app.command("protect")
def chain_protect(
    original_hash: Annotated[str, typer.Argument(help="Hash of the original data to protect.")],
    new_hash: Annotated[str, typer.Argument(help="Hash of the replacement/transformed data.")],
    description: Annotated[str, typer.Option("--description", "-d", help="Description of the transformation.")] = "",
    anchor_new: Annotated[bool, typer.Option("--anchor-new", help="Anchor the new hash if not already registered.")] = False,
    data_type: Annotated[str, typer.Option("--type", "-t", help="Data type for anchoring new hash.")] = "swarm-provenance",
    gas: Annotated[Optional[int], typer.Option("--gas", help="Explicit gas limit (skips estimation).")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
):
    """
    Protect original data by replacing it with a new version.

    This composite command:
    1. Verifies original is registered and ACTIVE
    2. Optionally anchors the new hash (--anchor-new)
    3. Records the transformation (original -> new)
    4. Sets original status to RESTRICTED
    """
    if gas is not None:
        _chain_config["gas_limit"] = gas
    try:
        client = _get_chain_client(verbose=verbose)
    except typer.Exit:
        raise

    results = {}

    # Step 1: Verify original is registered and ACTIVE
    try:
        record = client.get(original_hash, verbose=verbose)
    except exceptions.DataNotRegisteredError:
        typer.secho(f"ERROR: Original hash is not registered on-chain.", fg=typer.colors.RED, err=True)
        typer.echo(f"  Anchor it first: swarm-prov-upload chain anchor {original_hash}")
        raise typer.Exit(code=1)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    from .models import DataStatusEnum
    if record.status != DataStatusEnum.ACTIVE:
        typer.secho(
            f"ERROR: Original hash status is {record.status.name}, expected ACTIVE.",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=1)

    # Step 2: Optionally anchor new hash
    if anchor_new:
        try:
            anchor_result = client.anchor(new_hash, data_type=data_type, verbose=verbose)
            results["anchor"] = anchor_result
            if not output_json:
                typer.secho(f"New hash anchored.", fg=typer.colors.GREEN)
        except exceptions.DataAlreadyRegisteredError:
            # Already anchored is fine for protect — continue with transform
            if not output_json:
                typer.secho(f"New hash already anchored, continuing.", fg=typer.colors.YELLOW)
        except exceptions.ChainError as e:
            typer.secho(f"ERROR: Failed to anchor new hash: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    # Step 3: Record transformation
    try:
        transform_result = client.transform(original_hash, new_hash, description=description, verbose=verbose)
        results["transform"] = transform_result
        if not output_json:
            typer.secho(f"Transformation recorded.", fg=typer.colors.GREEN)
    except exceptions.ChainError as e:
        typer.secho(f"ERROR: Failed to record transformation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Step 4: Restrict original
    restrict_failed = False
    try:
        status_result = client.set_status(original_hash, status=1, verbose=verbose)
        results["restrict"] = status_result
        if not output_json:
            typer.secho(f"Original hash restricted.", fg=typer.colors.GREEN)
    except exceptions.ChainError as e:
        restrict_failed = True
        typer.secho(
            f"\nWARNING: Transform succeeded but failed to restrict original: {e}",
            fg=typer.colors.YELLOW, err=True,
        )
        typer.echo(f"  Restrict manually: swarm-prov-upload chain status {original_hash} --set restricted", err=True)

    if output_json:
        output = {}
        if "anchor" in results:
            output["anchor"] = results["anchor"].model_dump()
        output["transform"] = results["transform"].model_dump()
        output["restrict"] = results["restrict"].model_dump() if "restrict" in results else None
        output["partial_failure"] = restrict_failed
        typer.echo(json.dumps(output, indent=2))
        return

    if restrict_failed:
        typer.secho(f"\nProtect partially complete.", fg=typer.colors.YELLOW, bold=True)
        typer.echo(f"  Original:  {original_hash} (restrict failed)")
    else:
        typer.secho(f"\nProtect complete!", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"  Original:  {original_hash} -> RESTRICTED")
    typer.echo(f"  New:       {new_hash}")
    if description:
        typer.echo(f"  Desc:      {description}")


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[Optional[bool], typer.Option(
        "--version", "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    )] = None,
    backend: Annotated[Optional[str], typer.Option(
        "--backend", "-b",
        help="Backend to use: 'gateway' (default) or 'local'"
    )] = None,
    gateway_url: Annotated[Optional[str], typer.Option(
        "--gateway-url",
        help=f"Gateway URL (when backend=gateway). [default: {config.GATEWAY_URL}]"
    )] = None,
    x402: Annotated[Optional[bool], typer.Option(
        "--x402",
        help="Enable x402 pay-per-request payments (USDC on Base chain)."
    )] = None,
    auto_pay: Annotated[Optional[bool], typer.Option(
        "--auto-pay",
        help="Auto-pay without prompting (up to --max-pay limit)."
    )] = None,
    max_pay: Annotated[Optional[float], typer.Option(
        "--max-pay",
        help="Maximum auto-pay amount in USD per request. [default: 1.00]"
    )] = None,
    x402_network: Annotated[Optional[str], typer.Option(
        "--x402-network",
        help="x402 network: 'base-sepolia' (testnet) or 'base' (mainnet). [default: base-sepolia]"
    )] = None,
    chain: Annotated[Optional[str], typer.Option(
        "--chain",
        help="Blockchain for on-chain anchoring: 'base-sepolia' (testnet) or 'base' (mainnet)."
    )] = None,
    chain_rpc: Annotated[Optional[str], typer.Option(
        "--chain-rpc",
        help="Custom RPC URL for blockchain connection."
    )] = None,
    free: Annotated[Optional[bool], typer.Option(
        "--free",
        help="Use gateway free tier (X-Payment-Mode: free, rate-limited)."
    )] = None,
):
    """
    Swarm Provenance CLI Toolkit - Wraps and uploads data to Swarm.

    By default uses the provenance gateway (no local Bee node required).
    Use --backend local for direct Bee node communication.

    For pay-per-request mode, use --x402 to enable x402 payments.
    Requires X402_PRIVATE_KEY environment variable.

    For testing/development, use --free for rate-limited free tier access.
    """
    if backend:
        if backend not in ("gateway", "local"):
            typer.secho(f"ERROR: Invalid backend '{backend}'. Use 'gateway' or 'local'.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        _backend_config["backend"] = backend

    if gateway_url:
        _backend_config["gateway_url"] = gateway_url

    # x402 configuration
    if x402 is not None:
        _x402_config["enabled"] = x402
    if auto_pay is not None:
        _x402_config["auto_pay"] = auto_pay
    if max_pay is not None:
        _x402_config["max_auto_pay_usd"] = max_pay
    if x402_network:
        if x402_network not in ("base-sepolia", "base"):
            typer.secho(f"ERROR: Invalid x402 network '{x402_network}'. Use 'base-sepolia' or 'base'.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        _x402_config["network"] = x402_network

    # Free tier configuration
    if free is not None:
        _backend_config["free_tier"] = free

    # Chain configuration
    if chain:
        if chain not in ("base-sepolia", "base"):
            typer.secho(f"ERROR: Invalid chain '{chain}'. Use 'base-sepolia' or 'base'.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        _chain_config["chain"] = chain
    if chain_rpc:
        _chain_config["rpc_url"] = chain_rpc

if __name__ == "__main__":
     app()
