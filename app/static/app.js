"use strict";

const list = document.getElementById("recommendations");
if (list) {
  const cards = [...list.querySelectorAll(".recommendation")];
  const filters = [...document.querySelectorAll("[data-action-filter]")];
  const search = document.getElementById("search");
  const shownCount = document.getElementById("shown-count");
  const emptyState = document.getElementById("empty-state");
  const resetButton = document.getElementById("reset-filters");
  const filterLabel = document.getElementById("filter-label");
  let activeFilter = "all";

  function updateList() {
    const query = search.value.trim().toLocaleLowerCase();
    let count = 0;
    cards.forEach((card) => {
      const matchesAction = activeFilter === "all" || card.dataset.action === activeFilter;
      const matchesText = (card.dataset.trend || "").toLocaleLowerCase().includes(query);
      card.hidden = !(matchesAction && matchesText);
      if (!card.hidden) count += 1;
    });
    shownCount.textContent = `${count} of ${cards.length} recommendations shown`;
    emptyState.hidden = count !== 0;
    resetButton.hidden = activeFilter === "all" && query === "";
    filters.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.actionFilter === activeFilter)));
    const selected = filters.find((button) => button.dataset.actionFilter === activeFilter);
    filterLabel.textContent = selected?.querySelector(".action-card-label")?.textContent || "All actions";
  }

  filters.forEach((button) => {
    button.disabled = false;
    button.addEventListener("click", () => {
      activeFilter = button.dataset.actionFilter;
      updateList();
    });
  });
  search.disabled = false;
  search.addEventListener("input", updateList);
  resetButton.addEventListener("click", () => {
    activeFilter = "all";
    search.value = "";
    updateList();
    search.focus();
  });

  list.querySelectorAll(".details-toggle").forEach((button) => {
    const panel = document.getElementById(button.getAttribute("aria-controls"));
    panel.hidden = true;
    button.hidden = false;
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", () => {
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      panel.hidden = expanded;
    });
  });
}
