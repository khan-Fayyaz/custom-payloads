#!/usr/bin/env python3
"""
Sync upstream payload repositories and update payloads.json with latest releases.
Supports both stable releases and pre-releases.
Handles multiple asset extensions (.elf, .bin, etc.)
Automatically extracts .zip files to find payload binaries.
"""

import json
import requests
import sys
import os
import tempfile
import zipfile
from pathlib import Path

# Configuration
REPOS = [
    "drakmor/ShadowMountPlus",
    "drakmor/kstuff-lite",
    "aydencharles/onionHEN"
]

PAYLOAD_JSON_PATH = "payloads.json"
# Support multiple payload extensions
PAYLOAD_EXTENSIONS = [".elf", ".bin"]


def find_payload_in_directory(directory: str) -> dict:
    """
    Recursively search for a payload file (.elf or .bin) in a directory.
    
    Args:
        directory: Path to search in
    
    Returns:
        Dictionary with filename and relative path, or empty dict if not found
    """
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                for ext in PAYLOAD_EXTENSIONS:
                    if file.endswith(ext):
                        full_path = os.path.join(root, file)
                        return {
                            "filename": file,
                            "full_path": full_path
                        }
    except Exception as e:
        print(f"❌ Error searching directory {directory}: {e}")
    
    return {}


def extract_zip_and_find_payload(zip_path: str) -> dict:
    """
    Extract a ZIP file and search for payload binaries inside.
    
    Args:
        zip_path: Path to the ZIP file
    
    Returns:
        Dictionary with filename and extracted file path, or empty dict if not found
    """
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        print(f"   📦 Extracting ZIP to temporary directory: {temp_dir}")
        
        # Extract ZIP
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        print(f"   ✓ ZIP extracted successfully")
        
        # Search for payload in extracted content
        payload_info = find_payload_in_directory(temp_dir)
        
        if payload_info:
            print(f"   ✅ Found payload inside ZIP: {payload_info['filename']}")
            return payload_info
        else:
            supported_exts = ", ".join(PAYLOAD_EXTENSIONS)
            print(f"   ❌ No payload ({supported_exts}) found inside ZIP")
            return {}
    
    except zipfile.BadZipFile:
        print(f"   ❌ Invalid ZIP file: {zip_path}")
        return {}
    except Exception as e:
        print(f"   ❌ Error extracting ZIP: {e}")
        return {}


def download_file(url: str, save_path: str) -> bool:
    """
    Download a file from URL.
    
    Args:
        url: URL to download from
        save_path: Path to save the file
    
    Returns:
        True if successful, False otherwise
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        return True
    except Exception as e:
        print(f"   ❌ Error downloading file: {e}")
        return False


def get_latest_release(repo_url: str) -> dict:
    """
    Fetch the latest release (including pre-releases) for a repository.
    Handles both direct payload files and ZIP archives containing payloads.
    
    Args:
        repo_url: GitHub repository in format "owner/repo"
    
    Returns:
        Dictionary with version, filename, and url, or empty dict if failed
    """
    try:
        api_url = f"https://api.github.com/repos/{repo_url}/releases"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        releases = response.json()
        
        if not releases:
            print(f"❌ No releases found for {repo_url}")
            return {}
        
        # Get the latest release (first in the list)
        latest_release = releases[0]
        version = latest_release.get("tag_name") or latest_release.get("name")
        
        print(f"   Version: {version}")
        
        # First, try to find a direct payload asset (.elf, .bin)
        payload_asset = None
        for asset in latest_release.get("assets", []):
            asset_name = asset["name"]
            # Check if asset matches any supported extension
            for ext in PAYLOAD_EXTENSIONS:
                if asset_name.endswith(ext):
                    payload_asset = asset
                    print(f"   ✓ Found direct payload: {asset_name}")
                    break
            if payload_asset:
                break
        
        # If direct payload found, return it
        if payload_asset:
            return {
                "version": version,
                "filename": payload_asset["name"],
                "url": payload_asset["browser_download_url"]
            }
        
        # If no direct payload, look for ZIP file
        print(f"   ℹ️  No direct payload found, searching for ZIP archives...")
        zip_asset = None
        for asset in latest_release.get("assets", []):
            if asset["name"].endswith(".zip"):
                zip_asset = asset
                print(f"   📦 Found ZIP file: {asset['name']}")
                break
        
        if not zip_asset:
            supported_exts = ", ".join(PAYLOAD_EXTENSIONS)
            print(f"   ⚠️  No payload ({supported_exts}) or ZIP file found in {repo_url} release {version}")
            return {}
        
        # Download and extract ZIP to find payload
        temp_zip_path = os.path.join(tempfile.gettempdir(), zip_asset["name"])
        print(f"   ⬇️  Downloading ZIP file...")
        
        if not download_file(zip_asset["browser_download_url"], temp_zip_path):
            return {}
        
        # Extract ZIP and find payload
        payload_info = extract_zip_and_find_payload(temp_zip_path)
        
        # Clean up temporary ZIP
        try:
            os.remove(temp_zip_path)
        except:
            pass
        
        if not payload_info:
            return {}
        
        return {
            "version": version,
            "filename": payload_info["filename"],
            "url": zip_asset["browser_download_url"]  # Return the ZIP URL
        }
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to fetch {repo_url}: {e}")
        return {}
    except (KeyError, IndexError) as e:
        print(f"❌ Error parsing release data for {repo_url}: {e}")
        return {}


def load_payloads_json(path: str) -> dict:
    """Load payloads.json file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {path} not found")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Error: {path} is not valid JSON")
        sys.exit(1)


def save_payloads_json(data: dict, path: str) -> None:
    """Save payloads.json file with pretty formatting."""
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Successfully saved {path}")
    except IOError as e:
        print(f"❌ Error writing to {path}: {e}")
        sys.exit(1)


def update_payloads(payloads_data: dict) -> bool:
    """
    Update payloads with the latest release information from upstream repos.
    
    Args:
        payloads_data: The parsed payloads.json data
    
    Returns:
        True if any changes were made, False otherwise
    """
    payloads = payloads_data.get("payloads", [])
    
    if len(payloads) != len(REPOS):
        print(f"⚠️  Warning: Expected {len(REPOS)} payloads, found {len(payloads)}")
    
    changes_made = False
    
    for i, repo in enumerate(REPOS):
        if i >= len(payloads):
            print(f"⚠️  Skipping {repo}: not enough payloads in payloads.json")
            continue
        
        print(f"\n📦 Fetching latest release for {repo}...")
        release_info = get_latest_release(repo)
        
        if not release_info:
            print(f"⏭️  Skipping {repo}: no release info available")
            continue
        
        old_version = payloads[i].get("version", "unknown")
        new_version = release_info["version"]
        
        # Check if update is needed
        if old_version == new_version:
            print(f"✓ Payload {i} ({payloads[i]['name']}): Already up-to-date (v{old_version})")
            continue
        
        # Update the payload
        payloads[i]["version"] = release_info["version"]
        payloads[i]["filename"] = release_info["filename"]
        payloads[i]["url"] = release_info["url"]
        
        print(f"✅ Updated payload {i} ({payloads[i]['name']}): {old_version} → {new_version}")
        print(f"   Filename: {release_info['filename']}")
        print(f"   URL: {release_info['url']}")
        
        changes_made = True
    
    return changes_made


def main():
    """Main entry point."""
    print("=" * 70)
    print("🚀 PS5 Payload Manager - Upstream Release Sync")
    print("=" * 70)
    
    # Load current payloads.json
    print(f"\n📂 Loading {PAYLOAD_JSON_PATH}...")
    payloads_data = load_payloads_json(PAYLOAD_JSON_PATH)
    print(f"✓ Loaded {len(payloads_data.get('payloads', []))} payloads")
    
    # Display supported extensions
    supported_exts = ", ".join(PAYLOAD_EXTENSIONS)
    print(f"✓ Supported asset extensions: {supported_exts} (or within .zip files)")
    
    # Update payloads with latest releases
    print("\n" + "=" * 70)
    print("🔄 Checking upstream repositories for new releases...")
    print("=" * 70)
    
    changes_made = update_payloads(payloads_data)
    
    # Save updated payloads.json
    print("\n" + "=" * 70)
    if changes_made:
        print("💾 Saving changes to payloads.json...")
        save_payloads_json(payloads_data, PAYLOAD_JSON_PATH)
        print("\n✅ Sync completed successfully!")
        return 0
    else:
        print("ℹ️  No updates available")
        print("\n✓ Sync completed (no changes needed)")
        return 0


if __name__ == "__main__":
    sys.exit(main())