/* Student menu rendering and live availability updates. */
(function () {
  "use strict";

  const MAX_QTY = 10;

  function buildAddControls(item, browseOnly) {
    let quantity = 1;
    const wrap = QB.el("div", "add-controls");
    const stepper = QB.el("div", "stepper");
    const minus = QB.el("button", "step-btn", "−");
    const count = QB.el("span", "step-count", "1");
    const plus = QB.el("button", "step-btn", "+");
    minus.type = "button";
    plus.type = "button";
    minus.disabled = browseOnly;
    plus.disabled = browseOnly;
    minus.setAttribute("aria-label", "Decrease quantity");
    plus.setAttribute("aria-label", "Increase quantity");

    minus.addEventListener("click", () => {
      quantity = Math.max(1, quantity - 1);
      count.textContent = quantity;
    });
    plus.addEventListener("click", () => {
      quantity = Math.min(MAX_QTY, quantity + 1);
      count.textContent = quantity;
    });

    const add = QB.el("button", "btn btn-primary btn-small", "Add to cart");
    add.type = "button";
    if (browseOnly) {
      add.classList.add("disabled");
      add.setAttribute("aria-disabled", "true");
    }
    add.addEventListener("click", () => {
      if (browseOnly) {
        window.location.href = "/?message=login-required";
        return;
      }
      QB.addToCart(item.item_id, quantity);
      QB.toast(`Added ${quantity} × ${item.name} to your cart`, "success");
      quantity = 1;
      count.textContent = "1";
    });

    stepper.append(minus, count, plus);
    wrap.append(stepper, add);
    return wrap;
  }

  function buildCard(item, browseOnly) {
    const card = QB.el("article", "food-card");
    const media = QB.el("div", "food-media");
    if (item.image_url) {
      const img = QB.el("img");
      img.src = item.image_url;
      img.alt = item.name;
      img.loading = "lazy";
      img.decoding = "async";
      img.addEventListener("error", () => {
        img.remove();
        media.appendChild(QB.el("span", "food-emoji", item.emoji || "🍽️"));
      });
      media.appendChild(img);
    } else {
      media.appendChild(QB.el("span", "food-emoji", item.emoji || "🍽️"));
    }
    if (!item.available) media.appendChild(QB.el("span", "ribbon", "Sold Out"));

    const body = QB.el("div", "food-body");
    body.appendChild(QB.el("span", "tag", item.category));
    body.appendChild(QB.el("h3", "food-name", item.name));
    body.appendChild(QB.el("p", "food-desc", item.description));

    const footer = QB.el("div", "food-footer");
    footer.appendChild(QB.el("span", "price", QB.money(item.price)));
    if (item.available) {
      footer.appendChild(buildAddControls(item, browseOnly));
    } else {
      footer.appendChild(QB.el("span", "badge badge-muted", "Sold Out"));
    }
    body.appendChild(footer);
    card.append(media, body);
    return card;
  }

  function initMenuPage() {
    const grid = document.getElementById("menu-grid");
    const featuredGrid = document.getElementById("featured-grid");
    const featuredSection = document.getElementById("featured-section");
    const status = document.getElementById("menu-status");
    const empty = document.getElementById("menu-empty");
    const search = document.getElementById("menu-search");
    const chips = document.querySelector(".chips");
    const browseOnly = grid.closest(".menu-section").dataset.browseOnly === "true";
    let items = [];
    let category = "all";
    let menuSnapshot = "";

    function renderCategories(categories) {
      const choices = ["all", ...categories];
      if (!choices.includes(category)) category = "all";
      chips.replaceChildren(...choices.map((value) => {
        const label = value === "all" ? "All" : value;
        const chip = QB.el("button", "chip" + (category === value ? " active" : ""), label);
        chip.type = "button";
        chip.dataset.category = value;
        chip.setAttribute("aria-pressed", String(category === value));
        return chip;
      }));
    }

    function render() {
      const query = search.value.trim().toLowerCase();
      const visible = items.filter((item) => {
        const matchesCategory = category === "all" || item.category === category;
        const haystack = (item.name + " " + item.description + " " + item.category).toLowerCase();
        return matchesCategory && (!query || haystack.includes(query));
      });

      grid.replaceChildren(...visible.map((item) => buildCard(item, browseOnly)));
      empty.hidden = visible.length > 0;
      status.textContent = visible.length ? `${visible.length} item(s) shown` : "";

      const showFeatured = category === "all" && !query;
      featuredSection.hidden = !showFeatured;
      if (showFeatured) {
        featuredGrid.replaceChildren(...items.filter((item) => item.featured).map((item) => buildCard(item, browseOnly)));
      }
    }

    chips.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip");
      if (!chip) return;
      category = chip.dataset.category;
      chips.querySelectorAll(".chip").forEach((choice) => {
        const active = choice === chip;
        choice.classList.toggle("active", active);
        choice.setAttribute("aria-pressed", String(active));
      });
      render();
    });
    search.addEventListener("input", render);

    async function loadMenu() {
      try {
        const data = await QB.fetchJSON("/api/menu");
        const nextItems = data.items || [];
        const nextSnapshot = JSON.stringify([nextItems, data.categories || []]);
        if (nextSnapshot === menuSnapshot) return;
        menuSnapshot = nextSnapshot;
        items = nextItems;
        renderCategories(data.categories || []);
        render();
      } catch (err) {
        if (!menuSnapshot) {
          status.textContent = "";
          QB.toast("Could not load the menu. Please refresh the page.", "error");
          empty.hidden = false;
          empty.querySelector("p").textContent = "The menu is unavailable right now. Please try again shortly.";
        }
      }
    }

    loadMenu();
    window.setInterval(loadMenu, 5000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("menu-grid")) initMenuPage();
    const params = new URLSearchParams(window.location.search);
    if (params.get("completed") === "1") {
      QB.toast("Your order is complete. Thank you!", "success");
      window.history.replaceState(null, "", "/");
    }
  });
})();
