/* Staff dashboard (staff_dashboard.html). Staff can only move an order one step forward. */
(function () {
  "use strict";

  const root = document.getElementById("orders-body");
  if (!root) return;

  const REFRESH_MS = 5000;
  const NEXT = { Placed: "Preparing", Preparing: "Ready for Pickup", "Ready for Pickup": "Completed" };
  const ACTION_LABEL = { Preparing: "Start preparing", "Ready for Pickup": "Mark ready", Completed: "Mark completed" };
  const $ = (id) => document.getElementById(id);

  const state = {
    orders: [],          // all of today's orders (from the server)
    counts: {},
    filter: "all",
    query: "",
    knownIds: null,     // null until the first load, so existing orders are not flagged as new
    freshIds: new Set(),  // orders that arrived while this page is open
    timer: null,
  };

  function handleAuthError(err) {
    if (err.status === 401) {
      window.location.href = "/staff/login";
      return true;
    }
    return false;
  }

  function detectNewOrders(orders) {
    if (state.knownIds === null) {
      state.knownIds = new Set(orders.map((o) => o.order_id));
      return;
    }
    const arrived = orders.filter((o) => !state.knownIds.has(o.order_id));
    arrived.forEach((o) => state.freshIds.add(o.order_id));
    orders.forEach((o) => state.knownIds.add(o.order_id));
    if (arrived.length) {
      QB.toast(arrived.length === 1 ? "New order received: " + arrived[0].order_id : arrived.length + " new orders received", "success");
    }
  }

  function renderCounts() {
    document.querySelectorAll("[data-kpi]").forEach((el) => {
      el.textContent = state.counts[el.dataset.kpi] || 0;
    });
  }

  function td(content, className) {
    const cell = QB.el("td", className);
    if (content instanceof Node) cell.appendChild(content);
    else cell.textContent = content;
    return cell;
  }

  function buildRow(order) {
    const isFresh = state.freshIds.has(order.order_id);
    const tr = QB.el("tr", isFresh ? "is-new" : "");
    tr.dataset.id = order.order_id;

    const idCell = QB.el("div", "order-id-cell");
    idCell.appendChild(QB.el("strong", null, order.order_id));
    if (isFresh) idCell.appendChild(QB.el("span", "new-pill", "NEW"));

    const studentCell = QB.el("div");
    studentCell.appendChild(QB.el("div", null, order.student_name));
    if (order.student_id) studentCell.appendChild(QB.el("div", "student-sub", "ID: " + order.student_id));

    const itemsText = order.items.map((i) => `${i.quantity}× ${i.name}`).join(", ");
    const itemsCell = td(itemsText, "items-cell");

    const statusCell = td(QB.el("span", QB.statusClass(order.status), order.status));

    const actionCell = td("");
    if (NEXT[order.status]) {
      const button = QB.el("button", "btn btn-primary btn-small", ACTION_LABEL[NEXT[order.status]]);
      button.type = "button";
      button.dataset.next = NEXT[order.status];
      button.dataset.id = order.order_id;
      actionCell.appendChild(button);
    } else {
      actionCell.appendChild(QB.el("span", "muted small", "Completed"));
    }
    if (order.payment_status !== "paid" && order.payment_status !== "paid_at_order") {
      const paidButton = QB.el("button", "btn btn-outline btn-small mark-paid-btn", "Mark paid");
      paidButton.type = "button";
      paidButton.dataset.payment = "paid";
      paidButton.dataset.id = order.order_id;
      actionCell.appendChild(paidButton);
    }

    const paid = order.payment_status === "paid" || order.payment_status === "paid_at_order";
    const paymentCell = QB.el("div", "payment-indicator " + (paid ? "is-paid" : "is-pending"));
    paymentCell.appendChild(QB.el("span", "payment-icon", paid ? "✓" : "◷"));
    const paymentLabel = order.payment_status === "paid_at_order"
      ? "Paid at order"
      : paid ? "Paid" : "Pay at pickup";
    paymentCell.appendChild(QB.el("span", null, paymentLabel));

    tr.append(
      td(idCell),
      td(QB.formatDateTime(order.created_at)),
      td(studentCell),
      td(order.student_phone),
      itemsCell,
      td(QB.money(order.total_amount)),
      statusCell,
      td(paymentCell),
      actionCell
    );
    return tr;
  }

  function renderTable() {
    const visible = state.orders
      .filter((o) => state.filter === "all"
        ? o.status !== "Completed"
        : state.filter === "completed" ? o.status === "Completed" : o.status === state.filter)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    root.replaceChildren(...visible.map(buildRow));
    $("orders-empty").hidden = visible.length > 0;
  }

  function renderHeader() {
    const now = new Date();
    $("dash-date").textContent = now.toLocaleDateString("en-IN", {
      weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Kolkata",
    });
  }

  async function loadOrders() {
    const params = new URLSearchParams();
    if (state.query) params.set("q", state.query);
    try {
      const data = await QB.fetchJSON("/api/staff/orders?" + params.toString());
      state.counts = data.counts || {};
      state.orders = data.orders || [];
      // Only detect new orders on the unfiltered view, so a search does not look like new arrivals.
      if (!state.query) detectNewOrders(state.orders);
      renderCounts();
      renderTable();
      $("last-refreshed").textContent = "Updated " + new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Kolkata" });
    } catch (err) {
      if (!handleAuthError(err)) QB.toast(err.message, "error");
    }
  }

  function resultMessage(order, result) {
    if (result.status === "Ready for Pickup") {
      if (result.notification === "accepted") {
        return `${order.order_id} marked Ready. SMS accepted by Amazon SNS (handset delivery is not confirmed).`;
      }
      if (result.notification === "failed") {
        return `${order.order_id} marked Ready, but the SMS could not be sent. The order is still updated.`;
      }
      return `${order.order_id} marked Ready. SMS is disabled in this mode.`;
    }
    return `${order.order_id} is now ${result.status}.`;
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-next], button[data-payment]");
    if (!button) return;
    const id = button.dataset.id;
    const order = state.orders.find((o) => o.order_id === id) || { order_id: id };
    button.disabled = true;
    try {
      if (button.dataset.payment) {
        await QB.fetchJSON("/api/staff/orders/" + encodeURIComponent(id) + "/payment", {
          method: "PATCH",
          body: JSON.stringify({ payment_status: "paid" }),
        });
        QB.toast(id + " marked Paid.", "success");
        await loadOrders();
        return;
      }
      const result = await QB.fetchJSON("/api/staff/orders/" + encodeURIComponent(id) + "/status", {
        method: "PATCH",
        body: JSON.stringify({ status: button.dataset.next }),
      });
      QB.toast(resultMessage(order, result), result.notification === "failed" ? "error" : "success");
      await loadOrders();
    } catch (err) {
      if (handleAuthError(err)) return;
      QB.toast(err.message, "error");
      button.disabled = false;
      await loadOrders();
    }
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.filter = tab.dataset.filter;
      document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      renderTable();
    });
  });

  let searchTimer = null;
  $("staff-search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = event.target.value.trim();
      loadOrders();
    }, 300);
  });

  $("refresh-btn").addEventListener("click", loadOrders);

  renderHeader();
  loadOrders();
  state.timer = setInterval(loadOrders, REFRESH_MS);
})();
