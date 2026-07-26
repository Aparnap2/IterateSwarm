"""
ERPNext Connector — capability implementation of :class:`ERPConnector`.

Refactors the existing :mod:`src.integrations.erpnext` module into a class
that implements ``ERPConnector``.  Provides support, execution, team, and
finance data from an ERPNext (Frappé) instance.

Backward compatibility
----------------------
The old :func:`src.integrations.erpnext.get_erpnext_snapshot` is preserved
and delegates to this connector internally.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from .base import Connector, ConnectorConfig
from .erp import ERPConnector
from ..integrations.erpnext_client import ERPNextClient, ERPNextError
from ..integrations.retry import circuit_breaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Realistic mock seed data
# ---------------------------------------------------------------------------

_MOCK_ORDERS: list[dict[str, Any]] = [
    {"id": "SINV-001", "customer": "Acme Corp", "total_cents": 500000,
     "status": "submitted", "order_date": "2026-07-15"},
    {"id": "SINV-002", "customer": "Globex Inc", "total_cents": 1200000,
     "status": "draft", "order_date": "2026-07-20"},
    {"id": "SINV-003", "customer": "Initech", "total_cents": 350000,
     "status": "overdue", "order_date": "2026-06-01"},
    {"id": "SINV-004", "customer": "Stark Industries", "total_cents": 8000000,
     "status": "submitted", "order_date": "2026-07-25"},
]

_MOCK_INVENTORY: list[dict[str, Any]] = [
    {"item": "Widget A", "quantity": 150, "warehouse": "Main Storage"},
    {"item": "Widget B", "quantity": 42, "warehouse": "Main Storage"},
    {"item": "Gadget X", "quantity": 8, "warehouse": "Overflow"},
    {"item": "Component Y", "quantity": 500, "warehouse": "Raw Materials"},
]

_MOCK_SUPPLIERS: list[dict[str, Any]] = [
    {"id": "SUP-001", "name": "PartsCo Ltd", "status": "active"},
    {"id": "SUP-002", "name": "RawMaterial Inc", "status": "active"},
    {"id": "SUP-003", "name": "Logistics Pro", "status": "inactive"},
]

# ---------------------------------------------------------------------------
# Legacy snapshot mock data (preserved from original erpnext.py)
# ---------------------------------------------------------------------------

_MOCK_SUPPORT_DATA: dict[str, Any] = {
    "support_open_issues": 12,
    "support_unresolved_issues": 18,
    "support_open_priority_issues": 3,
}

_MOCK_EXECUTION_DATA: dict[str, Any] = {
    "execution_active_projects": 4,
    "execution_overdue_tasks": 7,
    "execution_milestones_total": 15,
    "execution_milestones_completed": 9,
    "execution_avg_completion": 62.5,
}

_MOCK_TEAM_DATA: dict[str, Any] = {
    "team_active_count": 18,
    "team_departments": {
        "Engineering": 8,
        "Product": 3,
        "Design": 2,
        "Marketing": 3,
        "Operations": 2,
    },
    "team_new_joinees_30d": 2,
}

_MOCK_FINANCE_DATA: dict[str, Any] = {
    "finance_unpaid_cents": 2400000,
    "finance_overdue_cents": 850000,
    "finance_total_outstanding_cents": 3250000,
}


class ERPNextConnector(ERPConnector):
    """ERPNext ERP connector.

    Parameters
    ----------
    config: ConnectorConfig
        If ``config.mock_mode`` is *True* or ERPNext URL is not configured,
        returns realistic seed data.

    Usage::

        config = ConnectorConfig(tenant_id="startup_abc", mock_mode=True)
        erp = ERPNextConnector(config)
        orders = erp.get_orders()
        inventory = erp.get_inventory()
    """

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._client: ERPNextClient | None = None
        # Auto-enable mock when ERPNext is not configured
        if not os.getenv("ERPNEXT_URL", "").strip():
            self.config.mock_mode = True

    def name(self) -> str:
        return "erpnext"

    # ------------------------------------------------------------------
    # Client lazy-init
    # ------------------------------------------------------------------

    def _get_client(self) -> ERPNextClient:
        if self._client is None:
            self._client = ERPNextClient()
        return self._client

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @circuit_breaker("erpnext")
    def health(self) -> dict[str, Any]:
        if self.config.mock_mode:
            return {"status": "ok", "latency_ms": 0, "source": "erpnext_mock"}

        import time

        start = time.monotonic()
        try:
            client = self._get_client()
            client.count("Issue", [["status", "!=", "Closed"]])
            elapsed = int((time.monotonic() - start) * 1000)
            return {"status": "ok", "latency_ms": elapsed, "source": "erpnext"}
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("ERPNext health check failed: %s", exc)
            return {"status": "down", "latency_ms": elapsed, "error": str(exc)}

    # ------------------------------------------------------------------
    # ERP methods
    # ------------------------------------------------------------------

    def get_orders(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [self._add_metadata(o, "erpnext_mock") for o in _MOCK_ORDERS]

        try:
            client = self._get_client()
            raw = client.list("Sales Invoice",
                              filters=[["status", "in", ["Draft", "Unpaid", "Partly Paid", "Overdue"]]],
                              fields=["name", "customer", "grand_total", "status", "posting_date"],
                              limit=5000)
            orders = []
            for inv in raw:
                orders.append(self._add_metadata({
                    "id": inv.get("name", ""),
                    "customer": inv.get("customer", ""),
                    "total_cents": int(float(inv.get("grand_total", 0) or 0) * 100),
                    "status": (inv.get("status", "") or "").lower(),
                    "order_date": (inv.get("posting_date", "") or "")[:10],
                }, "erpnext"))
            return orders
        except Exception as exc:
            logger.error("ERPNext get_orders failed: %s", exc)
            return [self._error_result("erpnext", error=str(exc))]

    def get_inventory(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [self._add_metadata(i, "erpnext_mock") for i in _MOCK_INVENTORY]

        try:
            client = self._get_client()
            raw = client.list("Bin",
                              fields=["item_code", "actual_qty", "warehouse"],
                              limit=5000)
            inventory = []
            for bin_rec in raw:
                inventory.append(self._add_metadata({
                    "item": bin_rec.get("item_code", ""),
                    "quantity": int(float(bin_rec.get("actual_qty", 0) or 0)),
                    "warehouse": bin_rec.get("warehouse", ""),
                }, "erpnext"))
            return inventory
        except Exception as exc:
            logger.error("ERPNext get_inventory failed: %s", exc)
            return [self._error_result("erpnext", error=str(exc))]

    def get_suppliers(self) -> list[dict[str, Any]]:
        if self.config.mock_mode:
            return [self._add_metadata(s, "erpnext_mock") for s in _MOCK_SUPPLIERS]

        try:
            client = self._get_client()
            raw = client.list("Supplier",
                              fields=["name", "supplier_name", "supplier_status"],
                              limit=5000)
            suppliers = []
            for sup in raw:
                suppliers.append(self._add_metadata({
                    "id": sup.get("name", ""),
                    "name": sup.get("supplier_name", ""),
                    "status": (sup.get("supplier_status", "") or "").lower(),
                }, "erpnext"))
            return suppliers
        except Exception as exc:
            logger.error("ERPNext get_suppliers failed: %s", exc)
            return [self._error_result("erpnext", error=str(exc))]

    # ------------------------------------------------------------------
    # Legacy snapshot support — used by the Startup Guardian orchestrator
    # Returns the flat dict format that the assemblers expect.
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        """Return a flat snapshot dict compatible with :mod:`src.guardian.assemblers`.

        This is the equivalent of the old ``get_erpnext_snapshot()`` function
        and is consumed by the backward-compatibility wrapper.
        """
        if self.config.mock_mode:
            combined = {
                **_MOCK_SUPPORT_DATA,
                **_MOCK_EXECUTION_DATA,
                **_MOCK_TEAM_DATA,
                **_MOCK_FINANCE_DATA,
            }
            return self._add_metadata(combined, "erpnext_mock")

        client = self._get_client()
        support = self._fetch_support_state(client)
        execution = self._fetch_execution_state(client)
        team = self._fetch_team_state(client)
        finance = self._fetch_finance_state(client)

        result = {**support, **execution, **team, **finance}
        logger.info(
            "ERPNext snapshot: support=%d unresolved, execution=%d active projects, "
            "team=%d active, finance=₹%d outstanding",
            result.get("support_unresolved_issues", 0),
            result.get("execution_active_projects", 0),
            result.get("team_active_count", 0),
            result.get("finance_total_outstanding_cents", 0) // 100,
        )
        return self._add_metadata(result, "erpnext")

    # ------------------------------------------------------------------
    # Internal snapshot fetch helpers (adapted from erpnext.py)
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_support_state(client: ERPNextClient) -> dict[str, Any]:
        result: dict[str, Any] = {
            "support_open_issues": 0,
            "support_unresolved_issues": 0,
            "support_open_priority_issues": 0,
        }
        try:
            result["support_open_issues"] = client.count("Issue", [["status", "!=", "Closed"]])
        except ERPNextError as e:
            logger.warning("Failed to count open issues: %s", e)
        try:
            result["support_unresolved_issues"] = client.count(
                "Issue", [["status", "!=", "Closed"], ["status", "!=", "Resolved"]]
            )
        except ERPNextError as e:
            logger.warning("Failed to count unresolved issues: %s", e)
        try:
            result["support_open_priority_issues"] = client.count(
                "Issue", [["priority", "=", "High"], ["status", "!=", "Closed"],
                          ["status", "!=", "Resolved"]]
            )
        except ERPNextError as e:
            logger.warning("Failed to count priority issues: %s", e)
        return result

    @staticmethod
    def _fetch_execution_state(client: ERPNextClient) -> dict[str, Any]:
        result: dict[str, Any] = {
            "execution_active_projects": 0,
            "execution_overdue_tasks": 0,
            "execution_milestones_total": 0,
            "execution_milestones_completed": 0,
            "execution_avg_completion": 0.0,
        }
        try:
            result["execution_active_projects"] = client.count("Project", [["status", "=", "Open"]])
        except ERPNextError as e:
            logger.warning("Failed to count active projects: %s", e)
        try:
            projects = client.list("Project", filters=[["status", "=", "Open"]],
                                   fields=["name", "percent_complete"], limit=1000)
            if projects:
                values = [p.get("percent_complete", 0) or 0 for p in projects]
                result["execution_avg_completion"] = round(sum(values) / len(values), 1)
        except ERPNextError as e:
            logger.warning("Failed to fetch project completion: %s", e)
        try:
            result["execution_overdue_tasks"] = client.count("Task", [["status", "=", "Overdue"]])
        except ERPNextError as e:
            logger.warning("Failed to count overdue tasks: %s", e)
        try:
            result["execution_milestones_total"] = client.count("Task", [["is_milestone", "=", 1]])
        except ERPNextError as e:
            logger.warning("Failed to count milestones: %s", e)
        try:
            result["execution_milestones_completed"] = client.count(
                "Task", [["is_milestone", "=", 1], ["status", "=", "Completed"]]
            )
        except ERPNextError as e:
            logger.warning("Failed to count completed milestones: %s", e)
        return result

    @staticmethod
    def _fetch_team_state(client: ERPNextClient) -> dict[str, Any]:
        result: dict[str, Any] = {
            "team_active_count": 0,
            "team_departments": {},
            "team_new_joinees_30d": 0,
        }
        try:
            result["team_active_count"] = client.count("Employee", [["status", "=", "Active"]])
        except ERPNextError as e:
            logger.warning("Failed to count active employees: %s", e)
        try:
            employees = client.list("Employee", filters=[["status", "=", "Active"]],
                                    fields=["name", "department", "date_of_joining"], limit=5000)
            dept_counts: dict[str, int] = {}
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            new_joinees = 0
            for emp in employees:
                dept = emp.get("department") or "Unassigned"
                dept_counts[dept] = dept_counts.get(dept, 0) + 1
                doj = emp.get("date_of_joining")
                if doj:
                    try:
                        join_date = datetime.strptime(str(doj)[:10], "%Y-%m-%d")
                        if join_date >= thirty_days_ago:
                            new_joinees += 1
                    except (ValueError, TypeError):
                        pass
            result["team_departments"] = dept_counts
            result["team_new_joinees_30d"] = new_joinees
        except ERPNextError as e:
            logger.warning("Failed to fetch employee details: %s", e)
        return result

    @staticmethod
    def _fetch_finance_state(client: ERPNextClient) -> dict[str, Any]:
        result: dict[str, Any] = {
            "finance_unpaid_cents": 0,
            "finance_overdue_cents": 0,
            "finance_total_outstanding_cents": 0,
        }
        try:
            unpaid = client.list("Sales Invoice",
                                 filters=[["status", "in", ["Unpaid", "Partly Paid"]]],
                                 fields=["name", "outstanding_amount"], limit=5000)
            unpaid_total = sum(
                float(inv.get("outstanding_amount", 0) or 0) for inv in unpaid
            )
            result["finance_unpaid_cents"] = int(unpaid_total * 100)
        except ERPNextError as e:
            logger.warning("Failed to fetch unpaid invoices: %s", e)
        try:
            overdue = client.list("Sales Invoice",
                                  filters=[["status", "=", "Overdue"]],
                                  fields=["name", "outstanding_amount"], limit=5000)
            overdue_total = sum(
                float(inv.get("outstanding_amount", 0) or 0) for inv in overdue
            )
            result["finance_overdue_cents"] = int(overdue_total * 100)
        except ERPNextError as e:
            logger.warning("Failed to fetch overdue invoices: %s", e)
        try:
            all_out = client.list("Sales Invoice",
                                  filters=[["status", "in", ["Unpaid", "Partly Paid", "Overdue"]]],
                                  fields=["name", "outstanding_amount"], limit=5000)
            outstanding_total = sum(
                float(inv.get("outstanding_amount", 0) or 0) for inv in all_out
            )
            result["finance_total_outstanding_cents"] = int(outstanding_total * 100)
        except ERPNextError as e:
            logger.warning("Failed to fetch total outstanding: %s", e)
        return result
