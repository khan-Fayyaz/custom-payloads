#!/usr/bin/env python3
"""
Sync upstream payload repositories and update payloads.json with latest releases.
Supports both stable releases and pre-releases.
Handles multiple asset extensions (.elf, .bin, etc.)
Automatically extracts .zip files and uploads extracted payloads to GitHub Pages.
"""

import json
import requests
import sys
import os
import tempfile
import zipfile
import shutil
import subprocess
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
# Directory where extracted payloads will be stored for GitHub Pages
PAYLOADS_DIR = "payloads"

# GitHub API Token (from environment variable)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def get_github_headers() -> dict:
    """
    Get request headers for GitHub API with authentication if available.
    
    Returns:
        Dictionary of headers with optional authorization
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
        print("✓ Using authenticated GitHub API (5000 requests/hour)")
    else:
        print("⚠️  Using unauthenticated GitHub API (60 requests/hour)")
        print("   Set GITHUB_TOKEN environment variable for higher limits")
    
    return headers


def find_payload_in_directory(directory: str) -> dict:
    """
    Recursively search for a payload file (.elf or .bin) in a directory.
    
    Args:
        directory: Path to search in
    
    Returns:
        Dictionary with filename and full path, or empty dict if not found
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


def download_file(url: str, save_path: str, headers: dict) -> bool:
    """
    Download a file from URL.
    
    Args:
        url: URL to download from
        save_path: Path to save the file
        headers: Request headers (with potential auth token)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        return True
    except Exception as e:
        print(f"   ❌ Error downloading file: {e}")
        return False


def copy_payload_to_pages(source_path: str, filename: str) -> bool:
    """
    Copy extracted payload to GitHub Pages directory.
    
    Args:
        source_path: Full path to the extracted payload
        filename: Filename to use in GitHub Pages
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure payloads directory exists
        if not os.path.exists(PAYLOADS_DIR):
            os.makedirs(PAYLOADS_DIR)
            print(f"   📁 Created directory: {PAYLOADS_DIR}")
        
        # Copy file to payloads directory
        dest_path = os.path.join(PAYLOADS_DIR, filename)
        shutil.copy2(source_path, dest_path)
        print(f"   ✓ Copied to: {dest_path}")
        
        return True
    except Exception as e:
        print(f"   ❌ Error copying payload: {e}")
        return False


def git_commit_and_push(filename: str) -> bool:
    """
    Commit and push the new payload file to Git.
    
    Args:
        filename: Name of the file that was added
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Stage the file
        subprocess.run(["git", "add", os.path.join(PAYLOADS_DIR, filename)], 
                      check=True, capture_output=True)
        
        # Check if there are changes to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], 
                               capture_output=True)
        
        if result.returncode == 0:
            print(f"   ℹ️  No changes to commit for {filename}")
            return True
        
        # Configure git if not already configured
        subprocess.run(["git", "config", "user.name", "Release Bot"], 
                      capture_output=True)
        subprocess.run(["git", "config", "user.email", "bot@github.com"], 
                      capture_output=True)
        
        # Commit
        subprocess.run(["git", "commit", "-m", f"chore: add extracted payload {filename}"],
                      check=True, capture_output=True)
        
        # Push
        subprocess.run(["git", "push"], check=True, capture_output=True)
        
        print(f"   ✅ Committed and pushed: {filename}")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Git error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Error in git operations: {e}")
        return False


def get_latest_release(repo_url: str, headers: dict) -> dict:
    """
    Fetch the latest release (including pre-releases) for a repository.
    Handles both direct payload files and ZIP archives containing payloads.
    For ZIP files, extracts and uploads to GitHub Pages.
    
    Args:
        repo_url: GitHub repository in format "owner/repo"
        headers: Request headers (with potential auth token)
    
    Returns:
        Dictionary with version, filename, and url, or empty dict if failed
    """
    try:
        api_url = f"https://api.github.com/repos/{repo_url}/releases"
        response = requests.get(api_url, timeout=10, headers=headers)
        response.raise_for_status()
        
        releases = response.json()
        
        if not releases:
            print(f"❌ No releases found for {repo_url}")
            return {}
        
        # Get the latest release (first in the list)
        latest_release = releases[0]
        version = latest_release.get("tag_name") or latest_release.get("name")
        
        print(f"   Version: {version}")
        
        # PRIORITY 1: Try to find a direct payload asset (.elf, .bin)
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
        
        # If direct payload found, return it immediately
        if payload_asset:
            return {
                "version": version,
                "filename": payload_asset["name"],
                "url": payload_asset["browser_download_url"]
            }
        
        # PRIORITY 2: Look for ZIP file
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
        
        if not download_file(zip_asset["browser_download_url"], temp_zip_path, headers):
            return {}
        
        # Extract ZIP and find payload
        payload_info = extract_zip_and_find_payload(temp_zip_path)
        
        if not payload_info:
            # Clean up temporary ZIP
            try:
                os.remove(temp_zip_path)
            except:
                pass
            return {}
        
        # Copy extracted payload to GitHub Pages directory
        print(f"   📤 Uploading extracted payload to GitHub Pages...")
        extracted_filename = payload_info["filename"]
        
        if copy_payload_to_pages(payload_info["full_path"], extracted_filename):
            # Commit and push to Git
            if git_commit_and_push(extracted_filename):
                # Clean up temporary ZIP
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
                
                # Return the GitHub Pages URL
                github_pages_url = f"https://khan-fayyaz.github.io/custom-payloads/payloads/{extracted_filename}"
                
                return {
                    "version": version,
                    "filename": extracted_filename,
                    "url": github_pages_url
                }
            else:
                print(f"   ⚠️  Failed to commit payload to Git")
                # Clean up temporary ZIP
                try:
                    os.remove(temp_zip_path)
                except:
                    pass
                return {}
        else:
            print(f"   ⚠️  Failed to copy payload to GitHub Pages")
            # Clean up temporary ZIP
            try:
                os.remove(temp_zip_path)
            except:
                pass
            return {}
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print(f"❌ Rate limit exceeded for {repo_url}")
            print(f"   💡 Tip: Set GITHUB_TOKEN environment variable for higher limits")
        else:
            print(f"❌ Failed to fetch {repo_url}: HTTP {e.response.status_code}")
        return {}
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


def update_payloads(payloads_data: dict, headers: dict) -> bool:
    """
    Update payloads with the latest release information from upstream repos.
    
    Args:
        payloads_data: The parsed payloads.json data
        headers: Request headers (with potential auth token)
    
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
        release_info = get_latest_release(repo, headers)
        
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
    
    # Get GitHub headers with auth if available
    print("\n🔐 Checking GitHub API authentication...")
    headers = get_github_headers()
    
    # Load current payloads.json
    print(f"\n📂 Loading {PAYLOAD_JSON_PATH}...")
    payloads_data = load_payloads_json(PAYLOAD_JSON_PATH)
    print(f"✓ Loaded {len(payloads_data.get('payloads', []))} payloads")
    
    # Display supported extensions
    supported_exts = ", ".join(PAYLOAD_EXTENSIONS)
    print(f"✓ Supported asset extensions: {supported_exts} (or within .zip files)")
    print(f"✓ Extracted payloads will be stored in: {PAYLOADS_DIR}/")
    
    # Update payloads with latest releases
    print("\n" + "=" * 70)
    print("🔄 Checking upstream repositories for new releases...")
    print("=" * 70)
    
    changes_made = update_payloads(payloads_data, headers)
    
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