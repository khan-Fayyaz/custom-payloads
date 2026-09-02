#!/usr/bin/env python3
"""
Sync upstream payload repositories and update payloads.json with latest releases.
Supports both stable releases and pre-releases.
Handles multiple asset extensions (.elf, .bin, etc.)
"""

import json
import requests
import sys
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


def get_latest_release(repo_url: str) -> dict:
    """
    Fetch the latest release (including pre-releases) for a repository.
    
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
        
        # Find the payload asset (.elf, .bin, or other supported extensions)
        payload_asset = None
        for asset in latest_release.get("assets", []):
            asset_name = asset["name"]
            # Check if asset matches any supported extension
            for ext in PAYLOAD_EXTENSIONS:
                if asset_name.endswith(ext):
                    payload_asset = asset
                    break
            if payload_asset:
                break
        
        if not payload_asset:
            supported_exts = ", ".join(PAYLOAD_EXTENSIONS)
            print(f"⚠️  No payload asset ({supported_exts}) found in {repo_url} release {version}")
            return {}
        
        return {
            "version": version,
            "filename": payload_asset["name"],
            "url": payload_asset["browser_download_url"]
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
    print(f"✓ Supported asset extensions: {supported_exts}")
    
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