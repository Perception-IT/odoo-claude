"""Odoo MCP Server — exposes Odoo XML-RPC API as MCP tools."""

import os
import xmlrpc.client
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP

# Load .env from project root if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

mcp = FastMCP("odoo")

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_config() -> dict[str, str]:
    url = os.environ.get("ODOO_URL", "")
    db = os.environ.get("ODOO_DB", "")
    username = os.environ.get("ODOO_USERNAME", "")
    password = os.environ.get("ODOO_API_KEY", os.environ.get("ODOO_PASSWORD", ""))
    if not all([url, db, username, password]):
        raise ValueError(
            "Missing Odoo credentials. Set ODOO_URL, ODOO_DB, ODOO_USERNAME, "
            "and ODOO_API_KEY (or ODOO_PASSWORD) environment variables."
        )
    return {"url": url, "db": db, "username": username, "password": password}


def _authenticate(cfg: dict) -> int:
    common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common")
    uid = common.authenticate(cfg["db"], cfg["username"], cfg["password"], {})
    if not uid:
        raise PermissionError("Odoo authentication failed — check credentials.")
    return uid


def _models(cfg: dict) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object")


def _exec(cfg: dict, uid: int, model: str, method: str, *args, **kwargs) -> Any:
    models = _models(cfg)
    return models.execute_kw(cfg["db"], uid, cfg["password"], model, method, list(args), kwargs)


def _connect():
    """Return (cfg, uid) after authenticating."""
    cfg = _get_config()
    uid = _authenticate(cfg)
    return cfg, uid


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def odoo_search_read(
    model: str,
    domain: list = None,
    fields: list = None,
    limit: int = 10,
    offset: int = 0,
    order: str = "",
) -> list[dict]:
    """Search Odoo records and return field values.

    Args:
        model: Odoo model technical name (e.g. 'res.partner', 'sale.order').
        domain: Search domain as list of tuples, e.g. [['is_company','=',True]].
                Leave empty for all records.
        fields: List of field names to return. Empty list returns all fields.
        limit: Maximum number of records (default 10, max 100).
        offset: Skip this many records (for pagination).
        order: Sort string, e.g. 'name asc' or 'date_order desc'.
    """
    cfg, uid = _connect()
    domain = domain or []
    fields = fields or []
    limit = min(limit, 100)
    kwargs: dict[str, Any] = {"limit": limit, "offset": offset}
    if fields:
        kwargs["fields"] = fields
    if order:
        kwargs["order"] = order
    return _exec(cfg, uid, model, "search_read", domain, **kwargs)


@mcp.tool()
def odoo_search(
    model: str,
    domain: list = None,
    limit: int = 10,
    offset: int = 0,
    order: str = "",
) -> list[int]:
    """Return IDs of Odoo records matching a domain.

    Args:
        model: Odoo model technical name.
        domain: Search domain (list of condition triples). Empty = all records.
        limit: Maximum IDs to return (default 10, max 1000).
        offset: Skip this many records.
        order: Sort string.
    """
    cfg, uid = _connect()
    domain = domain or []
    limit = min(limit, 1000)
    kwargs: dict[str, Any] = {"limit": limit, "offset": offset}
    if order:
        kwargs["order"] = order
    return _exec(cfg, uid, model, "search", domain, **kwargs)


@mcp.tool()
def odoo_read(model: str, ids: list[int], fields: list = None) -> list[dict]:
    """Read specific fields for given record IDs.

    Args:
        model: Odoo model technical name.
        ids: List of record IDs to read.
        fields: Fields to return. Empty list returns all fields.
    """
    cfg, uid = _connect()
    fields = fields or []
    kwargs = {"fields": fields} if fields else {}
    return _exec(cfg, uid, model, "read", ids, **kwargs)


@mcp.tool()
def odoo_create(model: str, values: dict) -> int:
    """Create a new Odoo record.

    Args:
        model: Odoo model technical name (e.g. 'res.partner').
        values: Dict of field_name -> value for the new record.

    Returns:
        ID of the newly created record.
    """
    cfg, uid = _connect()
    return _exec(cfg, uid, model, "create", values)


@mcp.tool()
def odoo_write(model: str, ids: list[int], values: dict) -> bool:
    """Update fields on existing Odoo records.

    Args:
        model: Odoo model technical name.
        ids: List of record IDs to update.
        values: Dict of field_name -> new value.

    Returns:
        True on success.
    """
    cfg, uid = _connect()
    return _exec(cfg, uid, model, "write", ids, values)


@mcp.tool()
def odoo_unlink(model: str, ids: list[int]) -> bool:
    """Delete Odoo records by ID.

    Args:
        model: Odoo model technical name.
        ids: List of record IDs to delete.

    Returns:
        True on success.
    """
    cfg, uid = _connect()
    return _exec(cfg, uid, model, "unlink", ids)


@mcp.tool()
def odoo_count(model: str, domain: list = None) -> int:
    """Count Odoo records matching a domain.

    Args:
        model: Odoo model technical name.
        domain: Search domain. Empty = count all records.

    Returns:
        Integer count.
    """
    cfg, uid = _connect()
    domain = domain or []
    return _exec(cfg, uid, model, "search_count", domain)


@mcp.tool()
def odoo_fields_get(model: str, attributes: list = None) -> dict:
    """Get field definitions for an Odoo model.

    Args:
        model: Odoo model technical name.
        attributes: Attributes to return per field (e.g. ['string','type','required']).
                    Empty returns all attributes.

    Returns:
        Dict of field_name -> field metadata.
    """
    cfg, uid = _connect()
    kwargs = {"attributes": attributes} if attributes else {}
    return _exec(cfg, uid, model, "fields_get", **kwargs)


@mcp.tool()
def odoo_call(model: str, method: str, ids: list[int], *args) -> Any:
    """Call an arbitrary method on Odoo records.

    Useful for business methods like action_confirm, action_invoice_create, etc.

    Args:
        model: Odoo model technical name.
        method: Method name to call.
        ids: List of record IDs to pass as first argument.
        *args: Additional positional arguments.

    Returns:
        Whatever the Odoo method returns.
    """
    cfg, uid = _connect()
    return _exec(cfg, uid, model, method, ids, *args)


@mcp.tool()
def odoo_name_search(model: str, name: str = "", domain: list = None, limit: int = 10) -> list:
    """Search records by display name (autocomplete-style).

    Args:
        model: Odoo model technical name.
        name: String to search for in the name field.
        domain: Additional filter domain.
        limit: Maximum results (default 10, max 100).

    Returns:
        List of [id, display_name] pairs.
    """
    cfg, uid = _connect()
    domain = domain or []
    limit = min(limit, 100)
    return _exec(cfg, uid, model, "name_search", name, domain, "ilike", limit)


@mcp.tool()
def odoo_get_server_version() -> dict:
    """Return Odoo server version information."""
    cfg = _get_config()
    common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common")
    return common.version()


@mcp.tool()
def odoo_list_models(filter_name: str = "") -> list[str]:
    """List available Odoo models, optionally filtered by name substring.

    Args:
        filter_name: Case-insensitive substring to filter model names.

    Returns:
        Sorted list of model technical names.
    """
    cfg, uid = _connect()
    domain: list = []
    if filter_name:
        domain = [["model", "ilike", filter_name]]
    records = _exec(cfg, uid, "ir.model", "search_read", domain, fields=["model"], limit=500)
    return sorted(r["model"] for r in records)


@mcp.tool()
def odoo_signup_stats_by_site(
    date_from: str = "",
    date_to: str = "",
) -> list[dict]:
    """Return player signup counts grouped by site and month.

    Uses sale_order.date_order (via x_sale_order_id) as the true signup date,
    NOT x_registration_submission.create_date which reflects Odoo ingestion time
    and is unreliable (records are often batch-imported after the fact).

    Args:
        date_from: ISO date string 'YYYY-MM-DD' (inclusive). Empty = no lower bound.
        date_to:   ISO date string 'YYYY-MM-DD' (inclusive). Empty = no upper bound.

    Returns:
        List of dicts with keys: month (YYYY-MM), site, players.
        Sorted by month then site.
    """
    cfg, uid = _connect()

    order_domain: list = []
    if date_from:
        order_domain.append(["date_order", ">=", date_from])
    if date_to:
        order_domain.append(["date_order", "<=", date_to])

    submissions = _exec(cfg, uid, "x_registration_submission", "search_read", [],
                        fields=["x_location_name", "x_players_count", "x_sale_order_id"],
                        limit=1000)

    order_ids = [r["x_sale_order_id"][0] for r in submissions if r.get("x_sale_order_id")]
    if not order_ids:
        return []

    domain: list = [["id", "in", order_ids]]
    if order_domain:
        domain += order_domain
    orders = _exec(cfg, uid, "sale.order", "search_read", domain,
                   fields=["date_order"], limit=1000)
    order_date_map = {o["id"]: o["date_order"][:7] for o in orders}

    from collections import defaultdict, Counter
    by_month_site: dict = defaultdict(Counter)
    for r in submissions:
        if not r.get("x_sale_order_id"):
            continue
        order_id = r["x_sale_order_id"][0]
        month = order_date_map.get(order_id)
        if not month:
            continue
        site = r.get("x_location_name") or "Unknown"
        by_month_site[month][site] += r.get("x_players_count") or 1

    result = []
    for month in sorted(by_month_site):
        for site, count in sorted(by_month_site[month].items()):
            result.append({"month": month, "site": site, "players": count})
    return result


if __name__ == "__main__":
    mcp.run()
