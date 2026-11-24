/* Cart page (cart.html) and checkout page (checkout.html).
 * Totals shown here are for display. The server recalculates every price when the order is placed.
 */
(function () {
  "use strict";

  const MAX_QTY = 10;
  let menuById = new Map();

  async function loadMenu() {
    const data = await QB.fetchJSON("/api/menu");
    menuById = new Map(data.items.map((item) => [item.item_id, item]));
  }

  // Remove cart lines whose items no longer exist on the menu.
  function pruneMissingItems() {
    const cart = QB.getCart();
    const kept = cart.filter((line) => menuById.has(line.item_id));
    if (kept.length !== cart.length) {
      QB.saveCart(kept);
      return true;
    }
    return false;
  }

  function cartDetails() {
    const lines = QB.getCart()
      .map((line) => {
        const item = menuById.get(line.item_id);
        return item ? { item: item, quantity: line.quantity, lineTotal: item.price * line.quantity } : null;
      })
      .filter(Boolean);
    const total = lines.reduce((sum, l) => sum + l.lineTotal, 0);
    const count = lines.reduce((sum, l) => sum + l.quantity, 0);
    const blocked = lines.some((l) => !l.item.available);
    return { lines: lines, total: total, count: count, blocked: blocked };
  }

  // ----- Cart page -----

  function cartRow(line) {
    const row = QB.el("div", "cart-row");
    row.dataset.id = line.item.item_id;

    const info = QB.el("div", "cart-info");
    info.appendChild(QB.el("span", "cart-emoji", line.item.emoji || "🍽️"));
    const text = QB.el("div");
    text.appendChild(QB.el("div", "cart-name", line.item.name));
    text.appendChild(QB.el("div", "muted small", QB.money(line.item.price) + " each"));
    if (!line.item.available) {
      text.appendChild(QB.el("div", "small", "Currently unavailable. Please remove this item."));
      text.lastChild.style.color = "var(--danger)";
    }
    info.appendChild(text);

    const controls = QB.el("div", "cart-controls");
    const minus = QB.el("button", "step-btn", "−");
    minus.dataset.action = "dec";
    minus.type = "button";
    minus.setAttribute("aria-label", "Decrease quantity");
    const count = QB.el("span", "step-count", String(line.quantity));
    const plus = QB.el("button", "step-btn", "+");
    plus.dataset.action = "inc";
    plus.type = "button";
    plus.disabled = line.quantity >= MAX_QTY;
    plus.setAttribute("aria-label", "Increase quantity");
    const stepper = QB.el("div", "stepper");
    stepper.append(minus, count, plus);
    const remove = QB.el("button", "remove-btn", "Remove");
    remove.dataset.action = "remove";
    remove.type = "button";
    controls.append(stepper, remove);

    row.append(info, controls, QB.el("strong", "line-total", QB.money(line.lineTotal)));
    return row;
  }

  function renderCart(container) {
    const details = cartDetails();
    container.replaceChildren(...details.lines.map(cartRow));

    document.getElementById("cart-empty").hidden = details.lines.length > 0;
    document.getElementById("summary-count").textContent = details.count;
    document.getElementById("summary-total").textContent = QB.money(details.total);

    const notice = document.getElementById("cart-notice");
    if (details.blocked) {
      notice.textContent = "Some items are unavailable. Remove them to continue to checkout.";
      notice.className = "notice error";
      notice.hidden = false;
    } else {
      notice.hidden = true;
    }

    const link = document.getElementById("checkout-link");
    const disabled = details.lines.length === 0 || details.blocked;
    link.classList.toggle("disabled", disabled);
    link.setAttribute("aria-disabled", String(disabled));
  }

  function initCartPage(container) {
    renderCart(container);

    container.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const id = button.closest(".cart-row").dataset.id;
      const line = QB.getCart().find((l) => l.item_id === id);
      const quantity = line ? line.quantity : 0;

      if (button.dataset.action === "inc") QB.setQuantity(id, Math.min(quantity + 1, MAX_QTY));
      if (button.dataset.action === "dec") QB.setQuantity(id, quantity - 1);
      if (button.dataset.action === "remove") QB.removeFromCart(id);
      renderCart(container);
    });

    document.getElementById("checkout-link").addEventListener("click", (event) => {
      if (event.currentTarget.getAttribute("aria-disabled") === "true") event.preventDefault();
    });
  }

  // ----- Checkout page -----

  function initCheckout(submitButton) {
    const details = cartDetails();
    if (details.lines.length === 0) {
      window.location.href = "/cart";
      return;
    }

    const list = document.getElementById("checkout-items");
    details.lines.forEach((line) => {
      const li = QB.el("li");
      li.append(
        QB.el("span", null, line.quantity + " × " + line.item.name),
        QB.el("span", null, QB.money(line.lineTotal))
      );
      list.appendChild(li);
    });
    document.getElementById("checkout-total").textContent = QB.money(details.total);

    const errorBox = document.getElementById("form-error");

    function showError(message) {
      errorBox.textContent = message;
      errorBox.hidden = false;
      errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    submitButton.addEventListener("click", async () => {
      errorBox.hidden = true;

      if (cartDetails().blocked) {
        return showError("Some items are unavailable. Go back to your cart and remove them.");
      }

      submitButton.disabled = true;
      submitButton.textContent = "Placing order…";
      try {
        const payload = {
          payment_method: document.querySelector('input[name="payment_method"]:checked').value,
          items: QB.getCart().map((l) => ({ item_id: l.item_id, quantity: l.quantity })),
        };
        const result = await QB.fetchJSON("/api/orders", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        QB.clearCart();
        window.location.href = "/confirmation/" + encodeURIComponent(result.order_id);
      } catch (err) {
        showError(err.message);
        submitButton.disabled = false;
        submitButton.textContent = "Place order";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const cartContainer = document.getElementById("cart-lines");
    const checkoutButton = document.getElementById("place-order-btn");
    if (!cartContainer && !checkoutButton) return;

    try {
      await loadMenu();
    } catch (err) {
      QB.toast("Could not load the menu. Please refresh the page.", "error");
      return;
    }

    if (pruneMissingItems()) {
      QB.toast("Some items were removed because they are no longer on the menu.", "info");
    }
    if (cartContainer) initCartPage(cartContainer);
    if (checkoutButton) initCheckout(checkoutButton);
  });
})();
