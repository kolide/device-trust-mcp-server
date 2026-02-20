"""Kolide K2 API client wrapper."""

import os
from typing import Any

import httpx
from dotenv import load_dotenv


class KolideAPIError(Exception):
    """Exception raised for Kolide API errors."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Kolide API error ({status_code}): {message}")


class KolideClient:
    """Async client for the Kolide K2 API.
    
    Reads the API key fresh from environment on each request,
    allowing for .env file updates without restart.
    """

    BASE_URL = "https://api.kolide.com"
    API_VERSION = "2023-05-26"

    def _get_api_key(self) -> str:
        """Get API key fresh from environment, reloading .env file."""
        # Reload .env file to pick up any changes
        load_dotenv(override=True)
        api_key = os.getenv("KOLIDE_API_KEY")
        if not api_key:
            raise KolideAPIError(401, "KOLIDE_API_KEY environment variable not set")
        return api_key

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with fresh API key."""
        return {
            "Authorization": f"Bearer {self._get_api_key()}",
            "x-kolide-api-version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        url = f"{self.BASE_URL}{path}"
        
        # Filter out None values from params
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data,
                timeout=30.0,
            )

            if response.status_code >= 400:
                raise KolideAPIError(response.status_code, response.text)

            if response.status_code == 204:
                return {"success": True}

            return response.json()

    # ===== Organization =====

    async def whoami(self) -> dict[str, Any]:
        """Fetch information about the organization."""
        return await self._request("GET", "/whoami")

    # ===== Audit Logs =====

    async def list_audit_logs(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Audit logs."""
        return await self._request(
            "GET",
            "/audit_logs",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_audit_log(self, audit_log_id: str) -> dict[str, Any]:
        """Fetch information for a specific Audit log."""
        return await self._request("GET", f"/audit_logs/{audit_log_id}")

    # ===== Auth Logs =====

    async def list_auth_logs(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Auth log sessions."""
        return await self._request(
            "GET",
            "/auth_logs",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_auth_log(self, auth_log_id: str) -> dict[str, Any]:
        """Fetch information for a specific Auth log session."""
        return await self._request("GET", f"/auth_logs/{auth_log_id}")

    # ===== Devices =====

    async def list_devices(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Devices."""
        return await self._request(
            "GET",
            "/devices",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_device(self, device_id: str) -> dict[str, Any]:
        """Fetch information for a specific Device."""
        return await self._request("GET", f"/devices/{device_id}")

    async def delete_device(self, device_id: str) -> dict[str, Any]:
        """Delete a specific Device."""
        return await self._request("DELETE", f"/devices/{device_id}")

    async def get_device_open_issues(
        self,
        device_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of open Issues for a Device."""
        return await self._request(
            "GET",
            f"/devices/{device_id}/open_issues",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def update_device_authentication_mode(
        self,
        device_id: str,
        authentication_mode: str,
    ) -> dict[str, Any]:
        """Update a Device's authentication mode."""
        return await self._request(
            "PATCH",
            f"/devices/{device_id}/authentication_mode",
            json_data={"authentication_mode": authentication_mode},
        )

    async def delete_device_registration(self, device_id: str) -> dict[str, Any]:
        """Delete a device registration."""
        return await self._request("DELETE", f"/devices/{device_id}/registration")

    async def create_check_refresh(
        self,
        device_id: str,
        check_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Check refresh for a device."""
        json_data = {}
        if check_ids:
            json_data["check_ids"] = check_ids
        return await self._request(
            "POST",
            f"/devices/{device_id}/check_refreshes",
            json_data=json_data if json_data else None,
        )

    async def get_device_check_results(
        self,
        device_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Check results for a Device."""
        return await self._request(
            "GET",
            f"/devices/{device_id}/check_results",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    # ===== Device Groups =====

    async def list_device_groups(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Device groups."""
        return await self._request(
            "GET",
            "/device_groups",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_device_group(self, device_group_id: str) -> dict[str, Any]:
        """Fetch information for a specific Device group."""
        return await self._request("GET", f"/device_groups/{device_group_id}")

    async def list_device_group_devices(
        self,
        device_group_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Devices in a Device group."""
        return await self._request(
            "GET",
            f"/device_groups/{device_group_id}/devices",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def add_device_to_group(
        self,
        device_group_id: str,
        device_id: str,
    ) -> dict[str, Any]:
        """Add a Device to a Device Group."""
        return await self._request(
            "POST",
            f"/device_groups/{device_group_id}/memberships",
            json_data={"device_id": device_id},
        )

    async def remove_device_from_group(
        self,
        device_group_id: str,
        membership_id: str,
    ) -> dict[str, Any]:
        """Remove a Device from a Device Group."""
        return await self._request(
            "DELETE",
            f"/device_groups/{device_group_id}/memberships/{membership_id}",
        )

    # ===== Issues =====

    async def list_issues(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Issues."""
        return await self._request(
            "GET",
            "/issues",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_issue(self, issue_id: str) -> dict[str, Any]:
        """Fetch information for a specific Issue."""
        return await self._request("GET", f"/issues/{issue_id}")

    # ===== People =====

    async def list_people(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of People."""
        return await self._request(
            "GET",
            "/people",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_person(self, person_id: str) -> dict[str, Any]:
        """Fetch information for a specific Person."""
        return await self._request("GET", f"/people/{person_id}")

    async def list_person_devices(
        self,
        person_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of registered Devices for a Person."""
        return await self._request(
            "GET",
            f"/people/{person_id}/registered_devices",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def list_person_issues(
        self,
        person_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of open Issues for a Person."""
        return await self._request(
            "GET",
            f"/people/{person_id}/open_issues",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def list_person_groups_for_person(
        self,
        person_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Person groups for a Person."""
        return await self._request(
            "GET",
            f"/people/{person_id}/person_groups",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def list_deprovisioned_people(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of deprovisioned people."""
        return await self._request(
            "GET",
            "/deprovisioned_people",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    # ===== Person Groups =====

    async def list_person_groups(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Person groups."""
        return await self._request(
            "GET",
            "/person_groups",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_person_group(self, person_group_id: str) -> dict[str, Any]:
        """Fetch information for a specific Person group."""
        return await self._request("GET", f"/person_groups/{person_group_id}")

    async def list_person_group_people(
        self,
        person_group_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of People in a Person group."""
        return await self._request(
            "GET",
            f"/person_groups/{person_group_id}/people",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    # ===== Checks =====

    async def list_checks(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Checks."""
        return await self._request(
            "GET",
            "/checks",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_check(self, check_id: str) -> dict[str, Any]:
        """Fetch information for a specific Check."""
        return await self._request("GET", f"/checks/{check_id}")

    async def get_check_results(
        self,
        check_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Check results."""
        return await self._request(
            "GET",
            f"/checks/{check_id}/results",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_check_configuration(self, check_id: str) -> dict[str, Any]:
        """Fetch the configuration for a specific Check."""
        return await self._request("GET", f"/checks/{check_id}/configurations")

    async def update_check_configuration(
        self,
        check_id: str,
        configuration: dict[str, Any],
    ) -> dict[str, Any]:
        """Update the configuration for a Check."""
        return await self._request(
            "PATCH",
            f"/checks/{check_id}/configurations",
            json_data=configuration,
        )

    # ===== Live Query Campaigns =====

    async def list_live_query_campaigns(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Live query campaigns."""
        return await self._request(
            "GET",
            "/live_query_campaigns",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_live_query_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Fetch information for a specific Live query campaign."""
        return await self._request("GET", f"/live_query_campaigns/{campaign_id}")

    async def create_live_query_campaign(
        self,
        query: str,
        name: str | None = None,
        description: str | None = None,
        device_ids: list[str] | None = None,
        device_group_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Live query campaign."""
        json_data: dict[str, Any] = {"query": query}
        if name:
            json_data["name"] = name
        if description:
            json_data["description"] = description
        if device_ids:
            json_data["device_ids"] = device_ids
        if device_group_ids:
            json_data["device_group_ids"] = device_group_ids
        return await self._request(
            "POST",
            "/live_query_campaigns",
            json_data=json_data,
        )

    async def update_live_query_campaign(
        self,
        campaign_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update a Live query campaign."""
        json_data: dict[str, Any] = {}
        if name:
            json_data["name"] = name
        if description:
            json_data["description"] = description
        return await self._request(
            "PATCH",
            f"/live_query_campaigns/{campaign_id}",
            json_data=json_data,
        )

    async def delete_live_query_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Delete a Live query campaign."""
        return await self._request("DELETE", f"/live_query_campaigns/{campaign_id}")

    async def get_live_query_results(
        self,
        campaign_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch results for a Live query campaign."""
        return await self._request(
            "GET",
            f"/live_query_campaigns/{campaign_id}/query_results",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    # ===== Exemption Requests =====

    async def list_exemption_requests(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Exemption requests."""
        return await self._request(
            "GET",
            "/exemption_requests",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_exemption_request(self, request_id: str) -> dict[str, Any]:
        """Fetch information for a specific Exemption request."""
        return await self._request("GET", f"/exemption_requests/{request_id}")

    async def update_exemption_request(
        self,
        request_id: str,
        status: str | None = None,
        reviewer_note: str | None = None,
    ) -> dict[str, Any]:
        """Update an Exemption request."""
        json_data: dict[str, Any] = {}
        if status:
            json_data["status"] = status
        if reviewer_note:
            json_data["reviewer_note"] = reviewer_note
        return await self._request(
            "PATCH",
            f"/exemption_requests/{request_id}",
            json_data=json_data,
        )

    # ===== Registration Requests =====

    async def list_registration_requests(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Registration requests."""
        return await self._request(
            "GET",
            "/registration_requests",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_registration_request(self, request_id: str) -> dict[str, Any]:
        """Fetch information for a specific Registration request."""
        return await self._request("GET", f"/registration_requests/{request_id}")

    async def update_registration_request(
        self,
        request_id: str,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update a Registration request."""
        json_data: dict[str, Any] = {}
        if status:
            json_data["status"] = status
        return await self._request(
            "PATCH",
            f"/registration_requests/{request_id}",
            json_data=json_data,
        )

    # ===== Packages =====

    async def list_packages(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Packages."""
        return await self._request(
            "GET",
            "/packages",
            params={"cursor": cursor, "per_page": per_page},
        )

    async def get_package(self, package_id: str) -> dict[str, Any]:
        """Fetch information for a specific Package."""
        return await self._request("GET", f"/packages/{package_id}")

    # ===== Admin Users =====

    async def list_admin_users(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Admin users."""
        return await self._request(
            "GET",
            "/admin_users",
            params={"cursor": cursor, "per_page": per_page, "query": query},
        )

    async def get_admin_user(self, admin_user_id: str) -> dict[str, Any]:
        """Fetch information for a specific Admin user."""
        return await self._request("GET", f"/admin_users/{admin_user_id}")

    # ===== Reporting Tables =====

    async def list_reporting_tables(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Reporting tables."""
        return await self._request(
            "GET",
            "/reporting/tables",
            params={"cursor": cursor, "per_page": per_page},
        )

    async def get_reporting_table(self, table_name: str) -> dict[str, Any]:
        """Fetch information for a specific Reporting table."""
        return await self._request("GET", f"/reporting/tables/{table_name}")

    async def get_table_records(
        self,
        table_name: str,
        cursor: str | None = None,
        per_page: int | None = None,
    ) -> dict[str, Any]:
        """Fetch records from a Reporting table."""
        return await self._request(
            "GET",
            f"/reporting/tables/{table_name}/table_records",
            params={"cursor": cursor, "per_page": per_page},
        )

    # ===== Report Queries =====

    async def list_report_queries(
        self,
        cursor: str | None = None,
        per_page: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a list of Report queries."""
        return await self._request(
            "GET",
            "/reporting/queries",
            params={"cursor": cursor, "per_page": per_page},
        )

    async def get_report_query(self, query_id: str) -> dict[str, Any]:
        """Fetch information for a specific Report query."""
        return await self._request("GET", f"/reporting/queries/{query_id}")

    async def get_report_query_results(
        self,
        query_id: str,
        cursor: str | None = None,
        per_page: int | None = None,
    ) -> dict[str, Any]:
        """Fetch results for a Report query."""
        return await self._request(
            "GET",
            f"/reporting/queries/{query_id}/results",
            params={"cursor": cursor, "per_page": per_page},
        )
