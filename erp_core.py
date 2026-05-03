"""Small dependency-free ERP domain and service layer.

The module exposes immutable-ish domain records plus query functions over an
``ERPData`` aggregate. Callers can use ``seed_erp_data`` for a deterministic
sample company, or construct their own records for tests and simulations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable


Money = Decimal


@dataclass(frozen=True)
class Product:
    id: str
    sku: str
    name: str
    unit_cost: Money
    unit_price: Money
    reorder_point: int


@dataclass(frozen=True)
class Vendor:
    id: str
    name: str
    payment_terms_days: int
    lead_time_days: int = 10
    reliability: float = 0.95
    supplied_skus: tuple[str, ...] = ()


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    payment_terms_days: int


@dataclass(frozen=True)
class InventoryItem:
    product_id: str
    quantity_on_hand: int
    quantity_reserved: int = 0

    @property
    def available_quantity(self) -> int:
        return self.quantity_on_hand - self.quantity_reserved


@dataclass(frozen=True)
class OrderLine:
    product_id: str
    quantity: int
    unit_price: Money

    @property
    def line_total(self) -> Money:
        return self.unit_price * Decimal(self.quantity)


@dataclass(frozen=True)
class PurchaseOrder:
    id: str
    vendor_id: str
    order_date: date
    expected_date: date
    status: str
    lines: tuple[OrderLine, ...]

    @property
    def total(self) -> Money:
        return sum_money(line.line_total for line in self.lines)


@dataclass(frozen=True)
class SalesOrder:
    id: str
    customer_id: str
    order_date: date
    requested_ship_date: date
    status: str
    lines: tuple[OrderLine, ...]

    @property
    def total(self) -> Money:
        return sum_money(line.line_total for line in self.lines)


@dataclass(frozen=True)
class Invoice:
    id: str
    customer_id: str
    invoice_date: date
    due_date: date
    status: str
    amount: Money
    amount_paid: Money = Decimal("0.00")

    @property
    def balance_due(self) -> Money:
        return self.amount - self.amount_paid


@dataclass(frozen=True)
class ERPData:
    products: tuple[Product, ...]
    vendors: tuple[Vendor, ...]
    customers: tuple[Customer, ...]
    inventory: tuple[InventoryItem, ...]
    purchase_orders: tuple[PurchaseOrder, ...]
    sales_orders: tuple[SalesOrder, ...]
    invoices: tuple[Invoice, ...]
    current_cash: Money = Decimal("0.00")


def money(value: str | int | float | Decimal) -> Money:
    """Normalize values into Decimal currency amounts."""

    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def status_key(status: str) -> str:
    """Normalize imported/display statuses for rule comparisons."""

    return str(status).strip().lower().replace("-", "_").replace(" ", "_")


def seed_erp_data(today: date | None = None) -> ERPData:
    """Return deterministic sample ERP data.

    ``today`` controls relative due dates so tests can assert delayed and
    overdue behavior without depending on the wall clock.
    """

    today = today or date.today()

    products = (
        Product("P-100", "BOLT-10", "10mm Bolt", money("0.18"), money("0.35"), 500),
        Product("P-200", "PUMP-A", "Pump Assembly", money("62.00"), money("110.00"), 20),
        Product("P-300", "SENSOR-T", "Temperature Sensor", money("12.50"), money("24.00"), 50),
        Product("P-400", "VALVE-S", "Safety Valve", money("18.75"), money("39.00"), 25),
    )
    vendors = (
        Vendor("V-10", "Northstar Fasteners", 30, 6, 0.96, ("BOLT-10", "SENSOR-T")),
        Vendor("V-20", "Metro Industrial Supply", 45, 14, 0.82, ("PUMP-A", "VALVE-S")),
    )
    customers = (
        Customer("C-10", "Apex Manufacturing", 30),
        Customer("C-20", "Beacon Field Services", 15),
    )
    inventory = (
        InventoryItem("P-100", 820, 120),
        InventoryItem("P-200", 14, 6),
        InventoryItem("P-300", 44, 10),
        InventoryItem("P-400", 28, 0),
    )
    purchase_orders = (
        PurchaseOrder(
            "PO-1001",
            "V-20",
            today - timedelta(days=18),
            today - timedelta(days=2),
            "open",
            (OrderLine("P-200", 12, money("61.00")),),
        ),
        PurchaseOrder(
            "PO-1002",
            "V-10",
            today - timedelta(days=3),
            today + timedelta(days=7),
            "open",
            (OrderLine("P-100", 1000, money("0.17")),),
        ),
        PurchaseOrder(
            "PO-0999",
            "V-20",
            today - timedelta(days=25),
            today - timedelta(days=8),
            "received",
            (OrderLine("P-300", 25, money("12.25")),),
        ),
    )
    sales_orders = (
        SalesOrder(
            "SO-5001",
            "C-10",
            today - timedelta(days=5),
            today + timedelta(days=2),
            "open",
            (
                OrderLine("P-200", 3, money("110.00")),
                OrderLine("P-300", 8, money("24.00")),
            ),
        ),
        SalesOrder(
            "SO-5002",
            "C-20",
            today - timedelta(days=1),
            today + timedelta(days=6),
            "allocated",
            (OrderLine("P-400", 5, money("39.00")),),
        ),
        SalesOrder(
            "SO-4999",
            "C-10",
            today - timedelta(days=20),
            today - timedelta(days=10),
            "shipped",
            (OrderLine("P-100", 200, money("0.35")),),
        ),
    )
    invoices = (
        Invoice(
            "INV-9001",
            "C-10",
            today - timedelta(days=45),
            today - timedelta(days=15),
            "open",
            money("1800.00"),
            money("300.00"),
        ),
        Invoice(
            "INV-9002",
            "C-20",
            today - timedelta(days=6),
            today + timedelta(days=9),
            "open",
            money("725.50"),
        ),
        Invoice(
            "INV-8999",
            "C-10",
            today - timedelta(days=60),
            today - timedelta(days=30),
            "paid",
            money("450.00"),
            money("450.00"),
        ),
    )

    return ERPData(
        products=products,
        vendors=vendors,
        customers=customers,
        inventory=inventory,
        purchase_orders=purchase_orders,
        sales_orders=sales_orders,
        invoices=invoices,
        current_cash=money("12500.00"),
    )


def low_stock_items(data: ERPData) -> list[tuple[Product, InventoryItem]]:
    """Products whose available inventory is at or below the reorder point."""

    inventory_by_product = {item.product_id: item for item in data.inventory}
    return [
        (product, inventory_by_product[product.id])
        for product in data.products
        if product.id in inventory_by_product
        and inventory_by_product[product.id].available_quantity <= product.reorder_point
    ]


def delayed_purchase_orders(
    data: ERPData, as_of: date | None = None
) -> list[PurchaseOrder]:
    """Open purchase orders with expected receipt dates before ``as_of``."""

    as_of = as_of or date.today()
    return [
        po
        for po in data.purchase_orders
        if status_key(po.status) in {"open", "partially_received"} and po.expected_date < as_of
    ]


def overdue_invoices(data: ERPData, as_of: date | None = None) -> list[Invoice]:
    """Unpaid invoices with due dates before ``as_of``."""

    as_of = as_of or date.today()
    return [
        invoice
        for invoice in data.invoices
        if status_key(invoice.status) != "paid" and invoice.balance_due > 0 and invoice.due_date < as_of
    ]


def inventory_value(data: ERPData) -> Money:
    """Total on-hand inventory valued at product unit cost."""

    products_by_id = {product.id: product for product in data.products}
    return sum_money(
        products_by_id[item.product_id].unit_cost * Decimal(item.quantity_on_hand)
        for item in data.inventory
        if item.product_id in products_by_id
    )


def open_sales_orders(data: ERPData) -> list[SalesOrder]:
    """Sales orders still requiring fulfillment."""

    closed_statuses = {"cancelled", "closed", "invoiced", "shipped"}
    return [order for order in data.sales_orders if status_key(order.status) not in closed_statuses]


def fulfillment_risks(data: ERPData) -> list[dict[str, object]]:
    """Open sales-order lines that would leave inventory below its reorder band."""

    products = {product.id: product for product in data.products}
    customers = {customer.id: customer for customer in data.customers}
    risks: list[dict[str, object]] = []

    for order in open_sales_orders(data):
        customer = customers.get(order.customer_id, Customer(order.customer_id, order.customer_id, 0))
        for line in order.lines:
            product = products.get(line.product_id)
            if product is None:
                continue
            inventory = _inventory_for_product(data, product.id)
            available = inventory.available_quantity if inventory is not None else 0
            projected_available = available - line.quantity
            if projected_available > product.reorder_point:
                continue
            next_po = _next_open_purchase_order_for_product(data, product.id)
            shortage = max(0, -projected_available)
            risks.append(
                {
                    "order_id": order.id,
                    "customer": customer.name,
                    "sku": product.sku,
                    "required": line.quantity,
                    "available": available,
                    "projected_available": projected_available,
                    "shortage": shortage,
                    "status": "Blocked" if shortage else "At risk",
                    "next_receipt": f"{next_po.id} on {next_po.expected_date}" if next_po else "No open PO",
                }
            )

    return sorted(risks, key=lambda item: (0 if item["status"] == "Blocked" else 1, str(item["order_id"]), str(item["sku"])))


def find_product(data: ERPData, reference: str) -> Product | None:
    """Find a product by SKU, ID, or loose product-name match."""

    normalized = _search_key(reference)
    for product in data.products:
        if normalized in {_search_key(product.id), _search_key(product.sku), _search_key(product.name)}:
            return product
    for product in data.products:
        if normalized and normalized in _search_key(product.name):
            return product
    return None


def find_vendor_for_product(data: ERPData, product: Product, vendor_id: str | None = None) -> Vendor:
    if vendor_id:
        for vendor in data.vendors:
            if _search_key(vendor.id) == _search_key(vendor_id) or _search_key(vendor.name) == _search_key(vendor_id):
                return vendor
        raise ValueError(f"Unknown vendor: {vendor_id}")

    candidates = [vendor for vendor in data.vendors if product.sku in vendor.supplied_skus]
    if not candidates:
        raise ValueError(f"No approved vendor supplies {product.sku}")
    return sorted(candidates, key=lambda vendor: (-vendor.reliability, vendor.lead_time_days, vendor.name))[0]


def reorder_quantity(data: ERPData, product: Product) -> int:
    inventory = _inventory_for_product(data, product.id)
    available = inventory.available_quantity if inventory else 0
    target = max(product.reorder_point * 2, product.reorder_point + 10)
    return max(target - available, 1)


def create_purchase_order(
    data: ERPData,
    product_reference: str,
    quantity: int | None = None,
    vendor_id: str | None = None,
    as_of: date | None = None,
) -> tuple[ERPData, PurchaseOrder]:
    as_of = as_of or date.today()
    product = find_product(data, product_reference)
    if product is None:
        raise ValueError(f"Unknown product: {product_reference}")
    quantity = quantity if quantity is not None else reorder_quantity(data, product)
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    vendor = find_vendor_for_product(data, product, vendor_id)
    purchase_order = PurchaseOrder(
        id=next_document_id((po.id for po in data.purchase_orders), "PO"),
        vendor_id=vendor.id,
        order_date=as_of,
        expected_date=as_of + timedelta(days=vendor.lead_time_days),
        status="open",
        lines=(OrderLine(product.id, quantity, product.unit_cost),),
    )
    return replace(data, purchase_orders=data.purchase_orders + (purchase_order,)), purchase_order


def receive_purchase_order(
    data: ERPData,
    purchase_order_id: str,
    as_of: date | None = None,
) -> tuple[ERPData, PurchaseOrder]:
    del as_of
    wanted = normalize_document_id(purchase_order_id, "PO")
    updated_purchase_orders: list[PurchaseOrder] = []
    received_order: PurchaseOrder | None = None
    quantity_by_product: dict[str, int] = {}

    for order in data.purchase_orders:
        if _search_key(order.id) != _search_key(wanted):
            updated_purchase_orders.append(order)
            continue
        if status_key(order.status) == "received":
            raise ValueError(f"{order.id} is already received")
        received_order = replace(order, status="received")
        updated_purchase_orders.append(received_order)
        for line in order.lines:
            quantity_by_product[line.product_id] = quantity_by_product.get(line.product_id, 0) + line.quantity

    if received_order is None:
        raise ValueError(f"Unknown purchase order: {purchase_order_id}")

    updated_inventory = _add_inventory_quantities(data.inventory, quantity_by_product)
    return replace(data, inventory=updated_inventory, purchase_orders=tuple(updated_purchase_orders)), received_order


def apply_invoice_payment(
    data: ERPData,
    invoice_id: str,
    amount: Money | str | int | float | None = None,
    as_of: date | None = None,
) -> tuple[ERPData, Invoice]:
    del as_of
    wanted = normalize_document_id(invoice_id, "INV")
    updated_invoices: list[Invoice] = []
    paid_invoice: Invoice | None = None
    payment_total = money("0.00")

    for invoice in data.invoices:
        if _search_key(invoice.id) != _search_key(wanted):
            updated_invoices.append(invoice)
            continue
        if invoice.balance_due <= 0 or status_key(invoice.status) == "paid":
            raise ValueError(f"{invoice.id} is already paid")
        payment = invoice.balance_due if amount is None else money(amount)
        if payment <= 0:
            raise ValueError("payment amount must be positive")
        if payment > invoice.balance_due:
            raise ValueError("payment amount cannot exceed invoice balance")
        new_paid = invoice.amount_paid + payment
        status = "paid" if new_paid >= invoice.amount else invoice.status
        paid_invoice = replace(invoice, amount_paid=new_paid, status=status)
        updated_invoices.append(paid_invoice)
        payment_total = payment

    if paid_invoice is None:
        raise ValueError(f"Unknown invoice: {invoice_id}")

    return replace(data, invoices=tuple(updated_invoices), current_cash=data.current_cash + payment_total), paid_invoice


def cash_projection(data: ERPData, as_of: date | None = None, days: int = 30) -> Money:
    """Project cash by adding receivables and subtracting open PO commitments.

    The projection includes unpaid invoice balances and open purchase order
    totals due within the date window ``as_of`` through ``as_of + days``.
    """

    if days < 0:
        raise ValueError("days must be non-negative")

    as_of = as_of or date.today()
    through = as_of + timedelta(days=days)
    expected_receipts = sum_money(
        invoice.balance_due
        for invoice in data.invoices
        if status_key(invoice.status) != "paid"
        and invoice.balance_due > 0
        and as_of <= invoice.due_date <= through
    )
    expected_payments = sum_money(
        po.total
        for po in data.purchase_orders
        if status_key(po.status) in {"open", "partially_received"}
        and as_of <= po.expected_date <= through
    )
    return data.current_cash + expected_receipts - expected_payments


def normalize_document_id(value: str, prefix: str) -> str:
    normalized = str(value).strip().upper().replace(" ", "-")
    if normalized.startswith(prefix + "-"):
        return normalized
    if normalized.startswith(prefix):
        suffix = normalized[len(prefix) :].lstrip("-")
        return f"{prefix}-{suffix}"
    digits = "".join(ch for ch in normalized if ch.isdigit())
    return f"{prefix}-{digits}" if digits else normalized


def next_document_id(existing_ids: Iterable[str], prefix: str) -> str:
    max_number = 0
    for value in existing_ids:
        normalized = normalize_document_id(value, prefix)
        digits = "".join(ch for ch in normalized if ch.isdigit())
        if digits:
            max_number = max(max_number, int(digits))
    return f"{prefix}-{max_number + 1}"


def _search_key(value: object) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _inventory_for_product(data: ERPData, product_id: str) -> InventoryItem | None:
    for item in data.inventory:
        if item.product_id == product_id:
            return item
    return None


def _next_open_purchase_order_for_product(data: ERPData, product_id: str) -> PurchaseOrder | None:
    candidates = [
        order
        for order in data.purchase_orders
        if status_key(order.status) in {"open", "partially_received"}
        and any(line.product_id == product_id for line in order.lines)
    ]
    return min(candidates, key=lambda order: order.expected_date) if candidates else None


def _add_inventory_quantities(
    inventory: tuple[InventoryItem, ...],
    quantity_by_product: dict[str, int],
) -> tuple[InventoryItem, ...]:
    remaining = dict(quantity_by_product)
    updated: list[InventoryItem] = []
    for item in inventory:
        delta = remaining.pop(item.product_id, 0)
        updated.append(replace(item, quantity_on_hand=item.quantity_on_hand + delta))
    for product_id, quantity in remaining.items():
        updated.append(InventoryItem(product_id, quantity))
    return tuple(updated)


def cash_projection_details(
    data: ERPData, as_of: date | None = None, days: int = 30, threshold: Money | None = None
) -> dict[str, Money | int]:
    """Return a cash projection with auditable inflow and outflow components."""

    if days < 0:
        raise ValueError("days must be non-negative")

    as_of = as_of or date.today()
    threshold = threshold or money("15000.00")
    through = as_of + timedelta(days=days)
    expected_inflows = sum_money(
        invoice.balance_due
        for invoice in data.invoices
        if status_key(invoice.status) != "paid"
        and invoice.balance_due > 0
        and as_of <= invoice.due_date <= through
    )
    expected_outflows = sum_money(
        po.total
        for po in data.purchase_orders
        if status_key(po.status) in {"open", "partially_received"}
        and as_of <= po.expected_date <= through
    )
    return {
        "current_cash": data.current_cash,
        "expected_inflows": expected_inflows,
        "expected_outflows": expected_outflows,
        "projected_cash": data.current_cash + expected_inflows - expected_outflows,
        "threshold": threshold,
        "days": days,
    }


def build_dashboard_data(data: ERPData | None = None, as_of: date | None = None) -> dict[str, object]:
    """Format ERP state for the local web dashboard."""

    as_of = as_of or date.today()
    data = data or seed_erp_data(as_of)
    products = {product.id: product for product in data.products}
    vendors = {vendor.id: vendor for vendor in data.vendors}
    customers = {customer.id: customer for customer in data.customers}
    projection = cash_projection_details(data, as_of)
    open_orders = open_sales_orders(data)
    low_stock = low_stock_items(data)
    delayed_pos = delayed_purchase_orders(data, as_of)
    overdue = overdue_invoices(data, as_of)

    inventory_rows = []
    for item in data.inventory:
        product = products.get(item.product_id)
        if product is None:
            continue
        status = "Low" if item.available_quantity <= product.reorder_point else "Healthy"
        if product.reorder_point < item.available_quantity <= product.reorder_point * 1.5:
            status = "Watch"
        inventory_rows.append(
            {
                "sku": product.sku,
                "item": product.name,
                "stock": item.available_quantity,
                "status": status,
            }
        )

    sales_rows = [
        {
            "id": order.id,
            "customer": customers.get(order.customer_id, Customer(order.customer_id, order.customer_id, 0)).name,
            "total": order.total,
            "status": order.status,
        }
        for order in data.sales_orders
    ]
    purchase_rows = [
        {
            "id": order.id,
            "supplier": vendors.get(order.vendor_id, Vendor(order.vendor_id, order.vendor_id, 0)).name,
            "total": order.total,
            "status": "Delayed" if order in delayed_pos else order.status,
        }
        for order in data.purchase_orders
    ]
    invoice_rows = [
        {
            "id": invoice.id,
            "customer": customers.get(invoice.customer_id, Customer(invoice.customer_id, invoice.customer_id, 0)).name,
            "amount": invoice.balance_due,
            "status": "Overdue" if invoice in overdue else invoice.status,
        }
        for invoice in data.invoices
    ]

    risk_flags: list[dict[str, str]] = []
    for product, item in low_stock:
        risk_flags.append(
            {
                "level": "High" if item.available_quantity <= max(1, product.reorder_point // 2) else "Medium",
                "title": f"Low stock: {product.sku}",
                "detail": f"{item.available_quantity} available against reorder point {product.reorder_point}.",
            }
        )
    for order in delayed_pos:
        vendor = vendors.get(order.vendor_id)
        risk_flags.append(
            {
                "level": "High",
                "title": f"Delayed PO: {order.id}",
                "detail": f"{vendor.name if vendor else order.vendor_id} was expected on {order.expected_date}.",
            }
        )
    for invoice in overdue:
        customer = customers.get(invoice.customer_id)
        risk_flags.append(
            {
                "level": "Medium",
                "title": f"Overdue invoice: {invoice.id}",
                "detail": f"{customer.name if customer else invoice.customer_id} has {invoice.balance_due} outstanding.",
            }
        )
    if projection["projected_cash"] < projection["threshold"]:
        risk_flags.append(
            {
                "level": "High",
                "title": "Cash below operating threshold",
                "detail": f"Projected cash is {projection['projected_cash']} over the next {projection['days']} days.",
            }
        )

    return {
        "kpis": [
            {"label": "Projected cash", "value": f"${projection['projected_cash']:,.0f}", "trend": "Next 30 days"},
            {"label": "Open sales orders", "value": str(len(open_orders)), "trend": f"${sum_money(order.total for order in open_orders):,.0f} open value"},
            {"label": "Inventory value", "value": f"${inventory_value(data):,.0f}", "trend": "At unit cost"},
            {"label": "Overdue AR", "value": f"${sum_money(invoice.balance_due for invoice in overdue):,.0f}", "trend": f"{len(overdue)} invoices"},
        ],
        "risk_flags": risk_flags,
        "roles": [
            {
                "role": "CFO",
                "summary": f"Projected cash is ${projection['projected_cash']:,.0f}; overdue AR is ${sum_money(invoice.balance_due for invoice in overdue):,.0f}.",
            },
            {
                "role": "Operations",
                "summary": f"{len(low_stock)} low-stock SKUs and {len(delayed_pos)} delayed purchase orders need review.",
            },
            {
                "role": "Procurement",
                "summary": f"Prioritize replenishment for {', '.join(product.sku for product, _ in low_stock) or 'no SKUs'}.",
            },
            {
                "role": "Sales",
                "summary": f"{len(open_orders)} open orders depend on available inventory and vendor receipts.",
            },
        ],
        "inventory": inventory_rows,
        "sales_orders": sales_rows,
        "purchase_orders": purchase_rows,
        "invoices": invoice_rows,
        "fulfillment_risks": fulfillment_risks(data),
    }


def get_dashboard_data() -> dict[str, object]:
    return build_dashboard_data()


def get_kpis() -> list[dict[str, str]]:
    return build_dashboard_data()["kpis"]  # type: ignore[return-value]


def get_risk_flags() -> list[dict[str, str]]:
    return build_dashboard_data()["risk_flags"]  # type: ignore[return-value]


def get_role_summaries() -> list[dict[str, str]]:
    return build_dashboard_data()["roles"]  # type: ignore[return-value]


def get_inventory() -> list[dict[str, object]]:
    return build_dashboard_data()["inventory"]  # type: ignore[return-value]


def get_sales_orders() -> list[dict[str, object]]:
    return build_dashboard_data()["sales_orders"]  # type: ignore[return-value]


def get_purchase_orders() -> list[dict[str, object]]:
    return build_dashboard_data()["purchase_orders"]  # type: ignore[return-value]


def get_invoices() -> list[dict[str, object]]:
    return build_dashboard_data()["invoices"]  # type: ignore[return-value]


def sum_money(values: Iterable[Money]) -> Money:
    return sum(values, Decimal("0.00"))
