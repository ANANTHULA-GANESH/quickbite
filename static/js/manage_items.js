/* Staff menu editing and availability controls. */
(function () {
  "use strict";

  const root = document.getElementById("menu-items-body");
  if (!root) return;

  let itemsSnapshot = "";
  const $ = (id) => document.getElementById(id);

  function authError(err) {
    if (err.status === 401) {
      window.location.href = "/staff/login";
      return true;
    }
    return false;
  }

  function buildItemRow(item) {
    const row = QB.el("tr");
    row.dataset.id = item.item_id;

    const nameCell = QB.el("td");
    const name = QB.el("input", "item-edit-input");
    name.type = "text";
    name.maxLength = 80;
    name.value = item.name;
    name.setAttribute("aria-label", "Item name");
    nameCell.appendChild(name);

    const categoryCell = QB.el("td", null, item.category);
    const priceCell = QB.el("td");
    const price = QB.el("input", "item-edit-input item-price-input");
    price.type = "number";
    price.min = "1";
    price.step = "1";
    price.value = item.price;
    price.setAttribute("aria-label", "Price in rupees");
    priceCell.appendChild(price);

    const availableCell = QB.el("td");
    const toggle = QB.el("button", "btn btn-small availability-toggle " + (item.available ? "is-available" : "is-unavailable"),
      item.available ? "Available" : "Not Available");
    toggle.type = "button";
    toggle.dataset.action = "availability";
    toggle.setAttribute("aria-pressed", String(item.available));
    toggle.setAttribute("aria-label", item.available ? "Mark not available" : "Mark available");
    availableCell.appendChild(toggle);

    const actionCell = QB.el("td");
    const save = QB.el("button", "btn btn-outline btn-small", "Save");
    save.type = "button";
    save.dataset.action = "save";
    actionCell.appendChild(save);

    row.append(nameCell, categoryCell, priceCell, availableCell, actionCell);
    return row;
  }

  function renderItems(items) {
    root.replaceChildren(...items.map(buildItemRow));
    $("items-empty").hidden = items.length > 0;
    $("items-last-refreshed").textContent = "Updated " + new Date().toLocaleTimeString("en-IN", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  }

  async function loadItems() {
    try {
      const data = await QB.fetchJSON("/api/staff/menu");
      const items = data.items || [];
      const snapshot = JSON.stringify(items);
      if (snapshot !== itemsSnapshot) {
        itemsSnapshot = snapshot;
        renderItems(items);
      }
    } catch (err) {
      if (!authError(err)) QB.toast(err.message, "error");
    }
  }

  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const row = button.closest("tr");
    const itemId = row.dataset.id;
    let update;

    if (button.dataset.action === "availability") {
      update = { available: button.getAttribute("aria-pressed") !== "true" };
    } else {
      const name = row.querySelector('input[aria-label="Item name"]').value.trim();
      const price = row.querySelector('input[aria-label="Price in rupees"]').value;
      if (!name || !/^\d+$/.test(price) || Number(price) < 1) {
        QB.toast("Enter an item name and a positive whole-number price.", "error");
        return;
      }
      update = { name: name, price: Number(price) };
    }

    button.disabled = true;
    try {
      await QB.fetchJSON("/api/staff/menu/" + encodeURIComponent(itemId), {
        method: "PATCH",
        body: JSON.stringify(update),
      });
      QB.toast("Menu item updated.", "success");
      await loadItems();
    } catch (err) {
      if (!authError(err)) QB.toast(err.message, "error");
      button.disabled = false;
    }
  });

  $("add-item-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    const price = form.elements.price.value;
    if (!/^\d+$/.test(price) || Number(price) < 1) {
      QB.toast("Price must be a positive whole number.", "error");
      form.elements.price.focus();
      return;
    }
    button.disabled = true;
    try {
      await QB.fetchJSON("/api/staff/menu", {
        method: "POST",
        body: JSON.stringify({
          name: form.elements.name.value.trim(),
          price: Number(price),
          category: form.elements.category.value,
          image_url: form.elements.image_url.value.trim(),
          available: form.elements.available.value === "yes",
        }),
      });
      form.reset();
      QB.toast("Menu item added.", "success");
      await loadItems();
    } catch (err) {
      if (!authError(err)) QB.toast(err.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  loadItems();
  window.setInterval(loadItems, 5000);
})();
