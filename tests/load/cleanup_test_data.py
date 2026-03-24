#!/usr/bin/env python3
"""
Cleanup test data created during load testing
Removes workspaces, projects, and features with specific prefixes
"""

import argparse
import asyncio
import httpx
import sys
from typing import List, Dict, Any


class TestDataCleanup:
    """Cleanup test data"""

    def __init__(self, base_url: str, prefix: str):
        self.base_url = base_url
        self.prefix = prefix
        self.client = httpx.AsyncClient(timeout=30.0)

    async def check_health(self) -> bool:
        """Check if backend is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Backend health check failed: {e}")
            return False

    async def list_workspaces(self) -> List[Dict[str, Any]]:
        """List all workspaces"""
        try:
            response = await self.client.get(f"{self.base_url}/api/workspaces")
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"❌ Error listing workspaces: {e}")
            return []

    async def delete_workspace(self, workspace_id: str, workspace_name: str) -> bool:
        """Delete a workspace"""
        # Note: The API doesn't have a delete workspace endpoint yet
        # This would need to be implemented in the backend
        print(f"  ⚠️  Would delete workspace: {workspace_name} ({workspace_id})")
        print(f"      (Delete endpoint not implemented yet)")
        return True

    async def cleanup_test_data(self, dry_run: bool = False) -> None:
        """Cleanup all test data matching prefix"""
        print(f"\n🧹 Cleaning up test data with prefix: '{self.prefix}'")
        if dry_run:
            print("  (DRY RUN - no actual deletions)")
        print()

        # Check backend health
        if not await self.check_health():
            print("❌ Backend is not healthy. Please start it first.")
            return

        # List all workspaces
        workspaces = await self.list_workspaces()
        print(f"Found {len(workspaces)} workspaces")

        # Filter workspaces by prefix
        matching_workspaces = [
            ws for ws in workspaces
            if ws.get('name', '').startswith(self.prefix)
        ]

        if not matching_workspaces:
            print(f"✓ No workspaces found with prefix '{self.prefix}'")
            return

        print(f"Found {len(matching_workspaces)} workspaces to delete:")
        for ws in matching_workspaces:
            print(f"  - {ws.get('name')} ({ws.get('id')})")

        if not dry_run:
            print("\n⚠️  Deleting workspaces...")
            for ws in matching_workspaces:
                await self.delete_workspace(ws['id'], ws['name'])
        else:
            print("\n(DRY RUN - skipping actual deletions)")

        print(f"\n✅ Cleanup complete!")

    async def cleanup(self):
        """Cleanup resources"""
        await self.client.aclose()


async def main():
    parser = argparse.ArgumentParser(description="Cleanup test data from RAPIDS load testing")
    parser.add_argument(
        "--prefix", type=str, default="load_test_",
        help="Prefix of test data to delete (default: load_test_)"
    )
    parser.add_argument(
        "--host", type=str, default="http://127.0.0.1:9403",
        help="Backend URL (default: http://127.0.0.1:9403)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be deleted without actually deleting"
    )

    args = parser.parse_args()

    cleaner = TestDataCleanup(args.host, args.prefix)
    try:
        await cleaner.cleanup_test_data(dry_run=args.dry_run)
    finally:
        await cleaner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
