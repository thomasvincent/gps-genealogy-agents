"""Browser-based authentication for FamilySearch.

This module provides automated browser login for FamilySearch using:
1. Direct Playwright automation
2. MCP browser server integration

Credentials are loaded with priority: params > env > config file
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)


@dataclass
class BrowserCredentials:
    """FamilySearch login credentials."""

    username: str
    password: str

    @classmethod
    def from_sources(
        cls,
        username: str | None = None,
        password: str | None = None,
        config_file: Path | None = None,
    ) -> BrowserCredentials | None:
        """Load credentials with priority: params > env > config.

        Args:
            username: Direct username parameter (highest priority)
            password: Direct password parameter (highest priority)
            config_file: Optional config file path (lowest priority)

        Returns:
            BrowserCredentials or None if not found
        """
        # Priority 1: Parameters
        if username and password:
            return cls(username=username, password=password)

        # Priority 2: Environment variables
        env_username = os.getenv("FAMILYSEARCH_USERNAME")
        env_password = os.getenv("FAMILYSEARCH_PASSWORD")
        if env_username and env_password:
            return cls(username=env_username, password=env_password)

        # Priority 3: Config file
        if config_file and config_file.exists():
            try:
                data = json.loads(config_file.read_text())
                file_username = data.get("familysearch_username")
                file_password = data.get("familysearch_password")
                if file_username and file_password:
                    return cls(username=file_username, password=file_password)
            except Exception as e:
                logger.debug(f"Failed to load credentials from config: {e}")

        return None


class FamilySearchBrowserAuth:
    """Browser automation for FamilySearch login.

    Supports both direct Playwright and MCP browser integration.
    """

    LOGIN_URL = "https://www.familysearch.org/auth/familysearch/login"
    TREE_URL = "https://www.familysearch.org/tree/pedigree/landscape"

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        config_file: Path | None = None,
    ) -> None:
        """Initialize browser authenticator.

        Args:
            headless: Run browser in headless mode
            timeout: Timeout in milliseconds for operations
            config_file: Optional config file for credentials
        """
        self.headless = headless
        self.timeout = timeout
        self.config_file = config_file or Path("data/credentials.json")

    async def login_with_playwright(
        self,
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """Login using Playwright and extract access token.

        Args:
            username: FamilySearch username (optional, loads from sources)
            password: FamilySearch password (optional, loads from sources)

        Returns:
            Access token string

        Raises:
            ValueError: If credentials not found or login failed
        """
        # Load credentials
        creds = BrowserCredentials.from_sources(username, password, self.config_file)
        if not creds:
            raise ValueError(
                "No FamilySearch credentials found. "
                "Provide username/password or set FAMILYSEARCH_USERNAME/PASSWORD env vars"
            )

        logger.info("Starting Playwright browser for FamilySearch login...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()

                # Navigate to login page
                logger.info("Navigating to FamilySearch login page...")
                await page.goto(self.LOGIN_URL, timeout=self.timeout)

                # Fill in credentials
                logger.info("Filling in credentials...")
                await page.fill('input[name="userName"]', creds.username)
                await page.fill('input[name="password"]', creds.password)

                # Click login button
                logger.info("Submitting login form...")
                await page.click('button[type="submit"]')

                # Wait for navigation to complete
                await page.wait_for_load_state("networkidle", timeout=self.timeout)

                # Check for errors
                error_el = await page.query_selector(".error-message, .alert-danger")
                if error_el:
                    error_text = await error_el.text_content()
                    raise ValueError(f"Login failed: {error_text}")

                # Navigate to tree to ensure full authentication
                logger.info("Navigating to family tree...")
                await page.goto(self.TREE_URL, timeout=self.timeout)
                await page.wait_for_load_state("networkidle", timeout=self.timeout)

                # Extract access token from cookies or localStorage
                logger.info("Extracting access token...")
                token = await self._extract_token(page, context)

                if not token:
                    raise ValueError("Failed to extract access token after login")

                logger.info("Successfully logged in and extracted token")
                return token

            finally:
                await browser.close()

    async def _extract_token(self, page: Page, context: BrowserContext) -> str | None:
        """Extract access token from browser state.

        Args:
            page: Playwright page object
            context: Playwright browser context

        Returns:
            Access token or None if not found
        """
        # Try localStorage first
        try:
            token = await page.evaluate(
                """() => {
                // Check localStorage
                const fsToken = localStorage.getItem('FS_AUTH_TOKEN');
                if (fsToken) return fsToken;

                // Check sessionStorage
                const sessionToken = sessionStorage.getItem('FS_AUTH_TOKEN');
                if (sessionToken) return sessionToken;

                // Check for token in any key containing 'token' or 'auth'
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && (key.toLowerCase().includes('token') ||
                               key.toLowerCase().includes('auth'))) {
                        const value = localStorage.getItem(key);
                        if (value && value.length > 20) {
                            return value;
                        }
                    }
                }

                return null;
            }"""
            )
            if token:
                return token
        except Exception as e:
            logger.debug(f"localStorage token extraction failed: {e}")

        # Try cookies
        try:
            cookies = await context.cookies()
            for cookie in cookies:
                if "token" in cookie["name"].lower() or "auth" in cookie["name"].lower():
                    if len(cookie["value"]) > 20:
                        return cookie["value"]
        except Exception as e:
            logger.debug(f"Cookie token extraction failed: {e}")

        # Try to extract from network requests
        try:
            # Look for Authorization headers in recent requests
            token = await page.evaluate(
                """() => {
                return new Promise((resolve) => {
                    const observer = new PerformanceObserver((list) => {
                        for (const entry of list.getEntries()) {
                            // Check if entry has Authorization header
                            // This is a simplified check - in practice, headers aren't
                            // directly accessible from PerformanceObserver
                        }
                        resolve(null);
                    });
                    observer.observe({ entryTypes: ['resource'] });
                    setTimeout(() => resolve(null), 1000);
                });
            }"""
            )
            if token:
                return token
        except Exception as e:
            logger.debug(f"Network token extraction failed: {e}")

        return None

    async def login_with_mcp(
        self,
        username: str | None = None,
        password: str | None = None,
        mcp_tools: dict[str, Any] | None = None,
    ) -> str:
        """Login using MCP browser server.

        Args:
            username: FamilySearch username
            password: FamilySearch password
            mcp_tools: MCP tool functions (browser_navigate, browser_type, etc.)

        Returns:
            Access token string

        Raises:
            ValueError: If credentials not found or MCP tools not provided
        """
        if not mcp_tools:
            raise ValueError("MCP tools not provided")

        # Load credentials
        creds = BrowserCredentials.from_sources(username, password, self.config_file)
        if not creds:
            raise ValueError("No FamilySearch credentials found")

        logger.info("Using MCP browser for FamilySearch login...")

        # Navigate to login page
        await mcp_tools["browser_navigate"](url=self.LOGIN_URL)

        # Fill credentials
        await mcp_tools["browser_type"](
            element="username field",
            ref='input[name="userName"]',
            text=creds.username,
        )
        await mcp_tools["browser_type"](
            element="password field",
            ref='input[name="password"]',
            text=creds.password,
        )

        # Submit form
        await mcp_tools["browser_click"](
            element="login button", ref='button[type="submit"]'
        )

        # Wait for navigation
        await asyncio.sleep(3)

        # Navigate to tree
        await mcp_tools["browser_navigate"](url=self.TREE_URL)
        await asyncio.sleep(2)

        # Extract token using evaluate
        token = await mcp_tools["browser_evaluate"](
            function="""() => {
            return localStorage.getItem('FS_AUTH_TOKEN') ||
                   sessionStorage.getItem('FS_AUTH_TOKEN');
        }"""
        )

        if not token:
            raise ValueError("Failed to extract access token via MCP")

        logger.info("Successfully logged in via MCP")
        return token


# Convenience function
async def login_familysearch(
    username: str | None = None,
    password: str | None = None,
    headless: bool = True,
    use_mcp: bool = False,
    mcp_tools: dict[str, Any] | None = None,
) -> str:
    """Convenience function to login to FamilySearch.

    Args:
        username: FamilySearch username
        password: FamilySearch password
        headless: Run browser in headless mode
        use_mcp: Use MCP browser instead of Playwright
        mcp_tools: MCP tool functions (required if use_mcp=True)

    Returns:
        Access token string
    """
    auth = FamilySearchBrowserAuth(headless=headless)

    if use_mcp:
        return await auth.login_with_mcp(username, password, mcp_tools)
    else:
        return await auth.login_with_playwright(username, password)
