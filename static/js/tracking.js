/* Student order tracking page (tracking.html). Read-only: students cannot change status. */
(function () {
  "use strict";

  const STEPS = ["Placed", "Preparing", "Ready for Pickup"];
  const STEP_LABELS = {
    Placed: "Order placed",
    Preparing: "Being prepared",
    "Ready for Pickup": "Ready for pickup",
  };
  const POLL_MS = 20000;

  const root = document.getElementById("tracking-root");
  if (!root) return;
  const orderId = root.dataset.orderId;
  const $ = (id) => document.getElementById(id);

  // No order ID in the URL yet: show the lookup form.
  if (!orderId) {
    $("lookup-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const id = $("lookup-input").value.trim().toUpperCase();
      if (id) window.location.href = "/track/" + encodeURIComponent(id);
    });
    return;
  }

  let pollTimer = null;

  function renderTimeline(order) {
    const timeline = $("t-timeline");
    timeline.replaceChildren(...STEPS.map((step, index) => {
      const li = QB.el("li", "step");
      if (index < order.status_index) li.classList.add("done");
      if (index === order.status_index) {
        li.classList.add("current");
        li.setAttribute("aria-current", "step");
      }
      const dot = QB.el("span", "dot", index < order.status_index ? "✓" : String(index + 1));
      li.append(dot, QB.el("div", null, STEP_LABELS[step]));
      return li;
    }));
  }

  function messageFor(order) {
    if (order.status === "Placed" || order.status === "Preparing") {
      return `Estimated preparation time: about ${order.estimated_prep_minutes} minutes. This is an estimate, not a guarantee.`;
    }
    if (order.status === "Ready for Pickup") {
      return "Your order is ready. Please collect it from the campus canteen counter.";
    }
    return "";
  }

  function render(order) {
    $("tracking-loading").hidden = true;
    $("tracking-error").hidden = true;
    $("tracking-body").hidden = false;

    $("t-order-id").textContent = order.order_id;
    const badge = $("t-status");
    badge.textContent = order.status;
    badge.className = QB.statusClass(order.status);

    renderTimeline(order);
    $("t-message").textContent = messageFor(order);

    $("t-items").replaceChildren(...order.items.map((item) => {
      const li = QB.el("li");
      li.append(
        QB.el("span", null, item.quantity + " × " + item.name),
        QB.el("span", null, QB.money(item.line_total))
      );
      return li;
    }));
    $("t-total").textContent = QB.money(order.total_amount);
    $("t-placed").textContent = "Placed on " + QB.formatDateTime(order.created_at);
    $("t-updated").textContent = "Last checked " + new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
  }

  async function load() {
    try {
      const order = await QB.fetchJSON("/api/orders/" + encodeURIComponent(orderId));
      if (order.status === "Completed") {
        window.location.href = "/?completed=1";
        return;
      }
      render(order);
    } catch (err) {
      $("tracking-loading").hidden = true;
      $("tracking-body").hidden = true;
      const box = $("tracking-error");
      box.textContent = err.message;
      box.hidden = false;
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }
  }

  $("refresh-btn").addEventListener("click", load);
  load();
  pollTimer = setInterval(load, POLL_MS);
})();
