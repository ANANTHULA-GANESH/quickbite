/* Student account profile order history. */
(function () {
  "use strict";

  const root = document.getElementById("account-orders");
  if (!root) return;

  const paymentLabels = {
    paid_at_order: "Paid at order",
    pay_at_pickup: "Pay at pickup",
    paid: "Paid",
  };

  function buildOrder(order) {
    const card = QB.el("article", "account-order-card");
    const heading = QB.el("div", "account-order-heading");
    heading.append(
      QB.el("strong", null, order.order_id),
      QB.el("span", QB.statusClass(order.status), order.status)
    );
    card.appendChild(heading);
    card.appendChild(QB.el("p", "muted small", QB.formatDateTime(order.created_at)));
    const items = QB.el("ul", "item-list");
    order.items.forEach((item) => {
      const line = QB.el("li");
      line.append(
        QB.el("span", null, item.quantity + " × " + item.name),
        QB.el("span", null, QB.money(item.line_total))
      );
      items.appendChild(line);
    });
    card.appendChild(items);
    card.appendChild(QB.el("p", "account-payment", "Payment: "
      + (paymentLabels[order.payment_status] || "Pay at pickup")
      + " · " + (order.payment_method === "online" ? "Pay Online" : "Pay at Counter")));
    card.appendChild(QB.el("strong", "account-order-total", "Total: " + QB.money(order.total_amount)));
    return card;
  }

  async function loadOrders() {
    try {
      const data = await QB.fetchJSON("/api/student/orders");
      const orders = data.orders || [];
      root.replaceChildren(...orders.map(buildOrder));
      document.getElementById("account-orders-empty").hidden = orders.length > 0;
      document.getElementById("account-orders-status").textContent =
        orders.length ? orders.length + " order(s)" : "";
    } catch (err) {
      if (err.status === 401) {
        window.location.href = "/";
        return;
      }
      document.getElementById("account-orders-status").textContent = err.message;
    }
  }

  loadOrders();
})();
