/* QuickBite shared helpers and the student menu page.
 * The cart stores only item IDs and quantities. Prices come from the server, never from here.
 */
(function () {
  "use strict";

  const CART_KEY = "quickbite_cart_v1";
  const MAX_QTY = 10;

  const QB = {
    money(amount) {
      return "₹" + Number(amount || 0).toLocaleString("en-IN");
    },

    formatDateTime(iso) {
      const date = new Date(iso);
      if (isNaN(date)) return iso || "";
      return date.toLocaleString("en-IN", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
      });
    },

    // ----- Cart (localStorage) -----
    getCart() {
      try {
        const raw = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
        if (!Array.isArray(raw)) return [];
        return raw
          .filter((l) => l && typeof l.item_id === "string" && Number.isInteger(l.quantity) && l.quantity > 0)
          .map((l) => ({ item_id: l.item_id, quantity: Math.min(l.quantity, MAX_QTY) }));
      } catch (err) {
        return [];
      }
    },

    saveCart(cart) {
      localStorage.setItem(CART_KEY, JSON.stringify(cart));
      QB.updateCartBadge();
    },

    cartCount() {
      return QB.getCart().reduce((sum, line) => sum + line.quantity, 0);
    },

    addToCart(itemId, quantity) {
      const cart = QB.getCart();
      const line = cart.find((l) => l.item_id === itemId);
      if (line) {
        line.quantity = Math.min(line.quantity + quantity, MAX_QTY);
      } else {
        cart.push({ item_id: itemId, quantity: Math.min(quantity, MAX_QTY) });
      }
      QB.saveCart(cart);
    },

    setQuantity(itemId, quantity) {
      if (quantity < 1) {
        QB.saveCart(QB.getCart().filter((l) => l.item_id !== itemId));
        return;
      }
      const cart = QB.getCart();
      cart.forEach((l) => { if (l.item_id === itemId) l.quantity = Math.min(quantity, MAX_QTY); });
      QB.saveCart(cart);
    },

    removeFromCart(itemId) {
      QB.saveCart(QB.getCart().filter((l) => l.item_id !== itemId));
    },

    clearCart() {
      QB.saveCart([]);
    },

    updateCartBadge() {
      const count = QB.cartCount();
      document.querySelectorAll("[data-cart-count]").forEach((el) => { el.textContent = count; });
    },

    // ----- UI helpers -----
    toast(message, type) {
      const container = document.getElementById("toast-container");
      if (!container) return;
      const el = document.createElement("div");
      el.className = "toast toast-" + (type || "info");
      el.setAttribute("role", "status");
      el.textContent = message;
      container.appendChild(el);
      setTimeout(() => el.classList.add("hide"), 3200);
      setTimeout(() => el.remove(), 3600);
    },

    el(tag, className, text) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined && text !== null) node.textContent = text;
      return node;
    },

    statusClass(status) {
      return "badge badge-" + String(status).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    },

    // ----- HTTP -----
    async fetchJSON(url, options) {
      const opts = options || {};
      const headers = { Accept: "application/json" };
      if (opts.body) headers["Content-Type"] = "application/json";
      const response = await fetch(url, {
        method: opts.method || "GET",
        body: opts.body,
        headers: headers,
        credentials: "same-origin",
      });
      let data = {};
      try { data = await response.json(); } catch (err) { /* response was not JSON */ }
      if (!response.ok) {
        const error = new Error(data.error || "Something went wrong. Please try again.");
        error.status = response.status;
        error.field = data.field || "";
        throw error;
      }
      return data;
    },
  };

  window.QB = QB;

  document.addEventListener("DOMContentLoaded", () => {
    QB.updateCartBadge();
  });
})();
