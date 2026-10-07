const tourData = [
  { icon: "search", title: "Find a book.", body: "Students can search the catalogue by title, author, subject or ISBN and immediately see whether a copy is available." },
  { icon: "book-open", title: "Borrow and track it.", body: "Every issue records the student, exact book copy, issue date, due date and current loan status in the database." },
  { icon: "graduation-cap", title: "Student portal.", body: "Students can view their borrowed books, due dates and borrowing history from one simple dashboard." },
  { icon: "library", title: "Librarian portal.", body: "The librarian manages books and students, issues available copies and records returns." }
];

document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.querySelector(".tour-dialog");
  const stage = dialog?.querySelector(".tour-stage");
  const steps = dialog?.querySelector(".tour-steps");
  let current = 0;

  const draw = () => {
    if (!stage || !steps) return;
    const item = tourData[current];
    steps.innerHTML = tourData.map((_, i) => `<button class="tour-step ${i === current ? "active" : ""}" data-step="${i}">${String(i + 1).padStart(2, "0")} ${["Search", "Borrow", "Student", "Librarian"][i]}</button>`).join("");
    stage.innerHTML = `<div class="tour-icon"><i data-lucide="${item.icon}"></i></div><div><p class="tour-count">Step ${current + 1} of ${tourData.length}</p><h3>${item.title}</h3><p>${item.body}</p></div>`;
    const next = dialog.querySelector("[data-tour-next]");
    next.innerHTML = current === tourData.length - 1 ? "Finish Tour" : `Next: ${["", "Borrow", "Student Portal", "Librarian Portal"][current + 1]} <i data-lucide="arrow-right"></i>`;
    dialog.querySelector("[data-tour-prev]").disabled = current === 0;
    lucide.createIcons();
  };

  document.querySelectorAll("[data-tour-open]").forEach(button => button.addEventListener("click", () => { current = 0; draw(); dialog.showModal(); }));
  dialog?.querySelector("[data-tour-close]")?.addEventListener("click", () => dialog.close());
  dialog?.querySelector("[data-tour-next]")?.addEventListener("click", () => { if (current === tourData.length - 1) dialog.close(); else { current += 1; draw(); } });
  dialog?.querySelector("[data-tour-prev]")?.addEventListener("click", () => { if (current > 0) { current -= 1; draw(); } });
  steps?.addEventListener("click", event => { const button = event.target.closest("[data-step]"); if (button) { current = Number(button.dataset.step); draw(); } });
  dialog?.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
  document.addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); document.querySelector(".global-search input")?.focus(); } });
  const sidebar = document.querySelector(".app-sidebar");
  document.querySelector("[data-sidebar]")?.addEventListener("click", () => sidebar?.classList.toggle("open"));

  const catalogSearch = document.querySelector("[data-catalog-search]");
  const resources = [...document.querySelectorAll("[data-resource]")];
  const filters = [...document.querySelectorAll("[data-filter]")];
  let activeFilter = "all";
  const filterCatalog = () => {
    const query = (catalogSearch?.value || "").trim().toLowerCase();
    let shown = 0;
    resources.forEach(resource => {
      const text = resource.dataset.search.toLowerCase();
      const matches = (!query || text.includes(query)) && (activeFilter === "all" || text.includes(activeFilter.toLowerCase()));
      resource.classList.toggle("hidden", !matches);
      if (matches) shown += 1;
    });
    const count = document.querySelector("[data-results]");
    if (count) count.textContent = `${shown} resource${shown === 1 ? "" : "s"}`;
  };
  catalogSearch?.addEventListener("input", filterCatalog);
  filters.forEach(filter => filter.addEventListener("click", () => {
    filters.forEach(item => item.classList.remove("active"));
    filter.classList.add("active"); activeFilter = filter.dataset.filter; filterCatalog();
  }));
  document.querySelector("[data-borrow]")?.addEventListener("click", event => {
    const button = event.currentTarget;
    button.innerHTML = '<i data-lucide="check"></i> Borrowed successfully';
    button.disabled = true; lucide.createIcons();
  });
  document.querySelector(".top-search input")?.addEventListener("keydown", event => {
    if (event.key === "Enter" && event.currentTarget.value.trim()) window.location.href = `/discover/?q=${encodeURIComponent(event.currentTarget.value.trim())}`;
  });
  const initialQuery = new URLSearchParams(location.search).get("q");
  if (initialQuery && catalogSearch) { catalogSearch.value = initialQuery; filterCatalog(); }
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const stage = document.querySelector(".product-stage");
    const depthItems = stage?.querySelectorAll(".book-card, .progress-card, .activity-card, .global-search");
    stage?.addEventListener("pointermove", event => {
      const rect = stage.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - .5;
      const y = (event.clientY - rect.top) / rect.height - .5;
      depthItems?.forEach((item, index) => {
        const depth = 4 + index * 2;
        item.style.translate = `${x * depth}px ${y * depth}px`;
      });
    });
    stage?.addEventListener("pointerleave", () => depthItems?.forEach(item => item.style.translate = "0 0"));
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) entry.target.classList.add("in-view");
    }), { threshold: .12 });
    document.querySelectorAll(".catalog-book, .collection-card, .analytics-card, .metric-grid article").forEach(item => observer.observe(item));
  }
  lucide.createIcons();
});
