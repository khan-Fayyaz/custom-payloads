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
												return {
														"filename": file
												}
		except Exception as e:
				print(f"   ❌ Error searching directory {directory}: {e}")
		
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
				return False


def fetch_release_info(repo_url: str, headers: dict) -> dict:
		"""
		Fetch release information (metadata only, no downloads).
		Returns version, filename, and whether it's a direct file or ZIP.
		
		Args:
				repo_url: GitHub repository in format "owner/repo"
				headers: Request headers (with potential auth token)
		
		Returns:
				Dictionary with release info, or empty dict if failed
		"""
		try:
				api_url = f"https://api.github.com/repos/{repo_url}/releases"
				response = requests.get(api_url, timeout=10, headers=headers)
				response.raise_for_status()
				
				releases = response.json()
				
				if not releases:
						return {}
				
				# Get the latest release (first in the list)
				latest_release = releases[0]
				version = latest_release.get("tag_name") or latest_release.get("name")
				
				# PRIORITY 1: Try to find a direct payload asset (.elf, .bin)
				for asset in latest_release.get("assets", []):
						asset_name = asset["name"]
						for ext in PAYLOAD_EXTENSIONS:
								if asset_name.endswith(ext):
										return {
												"version": version,
												"type": "direct",
												"filename": asset_name,
												"url": asset["browser_download_url"],
												"asset_data": asset
										}
				
				# PRIORITY 2: Look for ZIP file
				for asset in latest_release.get("assets", []):
						if asset["name"].endswith(".zip"):
								return {
										"version": version,
										"type": "zip",
										"zip_filename": asset["name"],
										"zip_url": asset["browser_download_url"],
										"asset_data": asset
								}
				
				# No suitable asset found
				return {}
		
		except requests.exceptions.HTTPError as e:
				if e.response.status_code == 403:
						print(f"   ❌ Rate limit exceeded for {repo_url}")
				else:
						print(f"   ❌ Failed to fetch {repo_url}: HTTP {e.response.status_code}")
				return {}
		except requests.exceptions.RequestException as e:
				print(f"   ❌ Failed to fetch {repo_url}: {e}")
				return {}
		except (KeyError, IndexError) as e:
				print(f"   ❌ Error parsing release data for {repo_url}: {e}")
				return {}


def process_zip_payload(repo_url: str, release_info: dict, headers: dict) -> dict:
		"""
		Process a ZIP file: download, extract, and prepare for upload.
		
		Args:
				repo_url: GitHub repository URL
				release_info: Release information from fetch_release_info()
				headers: Request headers
		
		Returns:
				Dictionary with processed payload info, or empty dict if failed
		"""
		try:
				zip_url = release_info["zip_url"]
				zip_filename = release_info["zip_filename"]
				version = release_info["version"]
				
				print(f"   📦 Processing ZIP file: {zip_filename}")
				
				# Download ZIP
				temp_zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
				print(f"   ⬇️  Downloading ZIP...")
				
				if not download_file(zip_url, temp_zip_path, headers):
						print(f"   ❌ Failed to download ZIP")
						return {}
				
				# Extract and find payload
				print(f"   📦 Extracting ZIP...")
				temp_extracted_zip_files_dir = None
				payload_filename = None
				try:
						# Create temporary directory
						temp_extracted_zip_files_dir = tempfile.mkdtemp()
				
						# Extract ZIP
						with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
								zip_ref.extractall(temp_extracted_zip_files_dir)
				
						# Search for payload in extracted content
						payload_info = find_payload_in_directory(temp_extracted_zip_files_dir)
				
						if payload_info:
								payload_filename = payload_info["filename"]
						else:
								print(f"   ❌ No payload found in ZIP")
								return {}
				
				except zipfile.BadZipFile:
						print(f"   ❌ BadZipFile exception occured while extracting zip")
						return {}
				except Exception as e:
						print(f"   ❌ exception occured while extracting zip: {e}")
						return {}

				# Copy to GitHub Pages
				print(f"   📤 Uploading to GitHub Pages...")
				if not copy_payload_to_pages(temp_extracted_zip_files_dir, payload_filename):
						print(f"   ❌ Failed to copy payload, skipping this update")
						return {}

				# Commit and push
				if not git_commit_and_push(payload_filename):
						print(f"   ❌ Failed to commit, skipping this update")
						return {}
				
				# Clean up temporary Zip file and extracted Zip files
				try:
						os.remove(temp_zip_path)
						shutil.rmtree(temp_extracted_zip_files_dir, ignore_errors=True)
				except Exception as e:
						print(f"Cleanup failed: {e}")
				
				print(f"   ✅ Found payload: {payload_filename}")
				return {
						"version": version,
						"type": "zip",
						"filename": payload_filename
				}
		
		except Exception as e:
				print(f"   ❌ Error processing ZIP: {e}")
				return {}


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
				payload_path = os.path.join(PAYLOADS_DIR, filename)
				
				# Stage the file
				subprocess.run(["git", "add", payload_path], check=True, capture_output=True)
				# Check if there are changes to commit
				result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
				if result.returncode == 0:
						print(f"   ℹ️  File already committed")
						return True
				
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
		payloads = payloads_data.get("payloads", [])
		print(f"✓ Loaded {len(payloads)} payloads")
		
		# Display supported extensions
		supported_exts = ", ".join(PAYLOAD_EXTENSIONS)
		print(f"✓ Supported asset extensions: {supported_exts}")
		
		# ==========================================
		# PHASE 1: FETCH AND COMPARE VERSIONS
		# ==========================================
		print("\n" + "=" * 70)
		print("📋 PHASE 1: Fetching release information and comparing versions...")
		print("=" * 70)
		
		release_infos = []
		updates_needed = []
		
		for i, repo in enumerate(REPOS):
				if i >= len(payloads):
						print(f"⚠️  Skipping {repo}: not enough payloads in payloads.json")
						continue
				
				print(f"\n📦 Checking {repo}...")
				release_info = fetch_release_info(repo, headers)
				
				if not release_info:
						print(f"   ⏭️  No suitable release found")
						release_infos.append(None)
						continue
				
				version = release_info.get("version")
				print(f"   ✓ Latest version: {version}")
				
				old_version = payloads[i].get("version", "unknown")
				
				if old_version == version:
						print(f"   ✓ Already up-to-date (v{old_version})")
						release_infos.append(None)
				else:
						print(f"   ⬆️  Update available: {old_version} → {version}")
						release_infos.append({
								"index": i,
								"repo": repo,
								"release_info": release_info,
								"old_version": old_version,
								"new_version": version
						})
						updates_needed.append(i)
		
		# ==========================================
		# PHASE 2: PROCESS UPDATES
		# ==========================================
		if not updates_needed:
				print("\n" + "=" * 70)
				print("ℹ️  No updates available")
				print("✓ Sync completed (no changes needed)")
				print("=" * 70)
				return 0
		
		print("\n" + "=" * 70)
		print(f"🔄 PHASE 2: Processing {len(updates_needed)} update(s)...")
		print("=" * 70)
		
		for update_info in release_infos:
				if update_info is None:
						continue
				
				i = update_info["index"]
				repo = update_info["repo"]
				release_info = update_info["release_info"]
				old_version = update_info["old_version"]
				new_version = update_info["new_version"]
				
				print(f"\n🔧 Processing {repo}...")
				print(f"   Updating: {old_version} → {new_version}")
				
				# Process based on release type
				if release_info["type"] == "direct":
						# Direct payload file
						print(f"   ✓ Direct payload file found")
						payloads[i]["version"] = new_version
						payloads[i]["filename"] = release_info["filename"]
						payloads[i]["url"] = release_info["url"]
						print(f"   ✅ Updated: {release_info['filename']}")
				
				elif release_info["type"] == "zip":
						# ZIP file - extract and process
						print(f"   Processing ZIP payload...")
						processed = process_zip_payload(repo, release_info, headers)
						
						if not processed:
								print(f"   ❌ Failed to process ZIP, skipping this update")
								continue
						
						filename = processed["filename"]
						
						# Update payloads.json
						github_pages_url = f"https://khan-fayyaz.github.io/custom-payloads/payloads/{filename}"
						payloads[i]["version"] = new_version
						payloads[i]["filename"] = filename
						payloads[i]["url"] = github_pages_url
						print(f"   ✅ Updated: {filename}")
		
		# ==========================================
		# PHASE 3: SAVE CHANGES
		# ==========================================
		print("\n" + "=" * 70)
		print("💾 PHASE 3: Saving changes...")
		print("=" * 70)
		
		save_payloads_json(payloads_data, PAYLOAD_JSON_PATH)
		print("\n✅ Sync completed successfully!")
		
		return 0


if __name__ == "__main__":
		sys.exit(main())