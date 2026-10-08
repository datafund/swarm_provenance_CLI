import requests
from urllib.parse import urljoin
import json
from typing import Optional

def purchase_postage_stamp(gateway_url: str, amount: int, depth: int, verbose: bool = False) -> str: # Added verbose
    headers = {"Content-Type": "application/json"}
    api_path = f"/stamps/{amount}/{depth}"
    url = urljoin(gateway_url, api_path)

    if verbose:
        print(f"\n--- DEBUG: Attempting Stamp Purchase ---")
        print(f"URL: POST {url}")
        print(f"Headers: {headers}")
        print(f"-------------------------------------\n")

    try:
        response = requests.post(url, headers=headers, timeout=120)
        if verbose:
            print(f"DEBUG: Stamp Purchase Response Status: {response.status_code}")
            # Consider adding response text preview if verbose and error
        response.raise_for_status()
        response_json = response.json()
        stamp_id = response_json.get("batchID")
        if not stamp_id:
             raise ValueError("API Response missing 'batchID' from purchase")
        if verbose:
            print(f"DEBUG: Successfully purchased Stamp ID: {stamp_id}")
        return stamp_id
    except requests.exceptions.RequestException as e:
        if verbose: print(f"ERROR_DETAIL: Stamp purchase request failed. URL: {url}, Error: {e}")
        raise ConnectionError(f"Stamp purchase failed for URL {url}: {e}") from e
    except (ValueError, KeyError) as e:
        response_text_debug = response.text if 'response' in locals() else 'N/A'
        if verbose: print(f"ERROR_DETAIL: Could not parse stamp purchase response. URL: {url}, Response Text: {response_text_debug}, Error: {e}")
        raise ValueError(f"Could not parse stamp purchase response from URL {url}: {e}") from e


def get_stamp_info(gateway_url: str, stamp_id: str, verbose: bool = False) -> Optional[dict]: # Added verbose
    api_path = f"/stamps/{stamp_id.lower()}"
    url = urljoin(gateway_url, api_path)

    if verbose:
        print(f"--- DEBUG: Checking Stamp Info ---")
        print(f"URL: GET {url}")
        print(f"--------------------------------\n")

    try:
        response = requests.get(url, timeout=10)
        if verbose:
            print(f"DEBUG: Get Stamp Info Response Status: {response.status_code}")
            # Consider response text preview if verbose and error
        if response.status_code == 404:
            if verbose: print(f"DEBUG: Stamp {stamp_id} not found (404).")
            return None
        response.raise_for_status()
        stamp_details = response.json()
        if not all(k in stamp_details for k in ("batchID", "usable", "depth", "amount")): # Basic check
            raise ValueError(f"Stamp info response for {stamp_id} missing expected fields.")
        return stamp_details
    except requests.exceptions.RequestException as e:
        if verbose: print(f"ERROR_DETAIL: Request to get stamp info failed. URL: {url}, Error: {e}")
        raise ConnectionError(f"Failed to get stamp info for {stamp_id} from URL {url}: {e}") from e
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        response_text_debug = response.text if 'response' in locals() else 'N/A'
        if verbose: print(f"ERROR_DETAIL: Could not parse stamp info response. URL: {url}, Response Text: {response_text_debug}, Error: {e}")
        raise ValueError(f"Could not parse stamp info for {stamp_id} from URL {url}: {e}") from e


def upload_data(gateway_url: str, data_to_upload: bytes, stamp_id: str, verbose: bool = False, content_type: str = "application/json") -> str: # Added verbose
    actual_stamp_id_for_header = stamp_id.lower()
    headers = {
         "Swarm-Postage-Batch-Id": actual_stamp_id_for_header,
         "Content-Type": content_type
         }
    api_path = "/bzz"
    url = urljoin(gateway_url, api_path)

    if verbose:
        print(f"\n--- DEBUG: Attempting Data Upload ---")
        print(f"URL: POST {url}")
        print(f"Headers: {json.dumps(headers, indent=2)}")
        data_preview = data_to_upload.decode('utf-8', errors='replace') if isinstance(data_to_upload, bytes) else str(data_to_upload)
        print(f"Data (first 200 chars): {data_preview[:200]}{'...' if len(data_preview) > 200 else ''}")
        print(f"-----------------------------------\n")

    try:
        response = requests.post(url, data=data_to_upload, headers=headers, timeout=60)
        if verbose:
            print(f"DEBUG: Data Upload Response Status: {response.status_code}")
            # Consider response text preview if verbose and error
        response.raise_for_status()
        response_json = response.json()
        swarm_hash = response_json.get("reference")
        if not swarm_hash:
             raise ValueError("API Response missing 'reference' from upload")
        if verbose:
            print(f"DEBUG: Successfully uploaded. Swarm Reference: {swarm_hash}")
        return swarm_hash
    except requests.exceptions.RequestException as e:
        if verbose: print(f"ERROR_DETAIL: Data upload request failed. URL: {url}, Headers: {headers}, Error: {e}")
        raise ConnectionError(f"Swarm upload failed for URL {url}: {e}") from e
    except (ValueError, KeyError) as e:
        response_text_debug = response.text if 'response' in locals() else 'N/A'
        if verbose: print(f"ERROR_DETAIL: Could not parse upload response. URL: {url}, Status: {response.status_code if 'response' in locals() else 'N/A'}, Response Text: {response_text_debug[:500]}..., Error: {e}")
        raise ValueError(f"Could not parse upload response from URL {url}: {e}") from e
        
        
def download_data_from_swarm(gateway_url: str, swarm_hash: str, verbose: bool = False) -> bytes:
    """
    Downloads data from Swarm via Bee Gateway using a Swarm reference hash.
    Returns the raw bytes of the content.
    """
    from .file_utils import is_swarm_reference
    if not is_swarm_reference(swarm_hash):
        raise ValueError(f"Not a Swarm reference (64 or 128 hex characters): {swarm_hash!r}")
    # Swarm hashes are typically lowercase, ensure it for the URL
    api_path = f"/bzz/{swarm_hash.lower()}" # Assuming data was uploaded via /bzz
    # If data could have been uploaded via /bytes, you might need a way to distinguish
    # or try /bzz first and then /bytes if it fails, though /bzz should retrieve single chunks too.
    url = urljoin(gateway_url, api_path)

    if verbose:
        print(f"\n--- DEBUG: Attempting Data Download ---")
        print(f"URL: GET {url}")
        print(f"-------------------------------------\n")

    try:
        response = requests.get(url, timeout=60) # Reasonably long timeout for download
        if verbose:
            print(f"DEBUG: Data Download Response Status: {response.status_code}")
            # Consider printing response headers if verbose and debugging
        
        if response.status_code == 404:
            raise FileNotFoundError(f"Data not found on Swarm at hash {swarm_hash} (404 from {url})")
        
        response.raise_for_status() # Raise HTTPError for other 4xx/5xx
        
        # The content is directly in response.content
        downloaded_bytes = response.content
        if verbose:
            print(f"DEBUG: Successfully downloaded {len(downloaded_bytes)} bytes.")
        return downloaded_bytes
    except requests.exceptions.RequestException as e:
        if verbose: print(f"ERROR_DETAIL: Data download request failed. URL: {url}, Error: {e}")
        raise ConnectionError(f"Swarm download failed for {swarm_hash} from URL {url}: {e}") from e
