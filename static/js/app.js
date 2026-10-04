const tourData = [
  { icon: "search", title: "Find knowledge in seconds.", body: "Search across books, research papers, journals, course material, authors, subjects and ISBNs from one command centre." },
  { icon: "sparkles", title: "Recommendations with academic context.", body: "Surface useful resources from subjects, reading activity and the courses a student is currently studying." },
  { icon: "book-open", title: "Move from discovery to access.", body: "Check availability, reserve a copy, borrow a book or open a permitted digital resource without breaking the journey." },
  { icon: "graduation-cap", title: "A personal academic workspace.", body: "Bring active loans, due dates, saved resources, reading progress and course-aware suggestions into one calm dashboard." },
  { icon: "chart-no-axes-combined", title: "Turn operations into intelligence.", body: "Help librarians understand demand, circulation, engagement and collection gaps—not simply maintain CRUD tables." }
];

document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.querySelector(".tour-dialog");
  const stage = dialog?.querySelector(".tour-stage");
  const steps = dialog?.querySelector(".tour-steps");
  let current = 0;

  const draw = () => {
    if (!stage || !steps) return;
    const item = tourData[current];
    steps.innerHTML = tourData.map((_, i) => `<button class="tour-step ${i === current ? "active" : ""}" data-step="${i}">${String(i + 1).padStart(2, "0")} ${["Search", "Recommend", "Borrow / Read", "Student", "Librarian"][i]}</button>`).join("");
    stage.innerHTML = `<div class="tour-icon"><i data-lucide="${item.icon}"></i></div><div><p class="tour-count">Step ${current + 1} of ${tourData.length}</p><h3>${item.title}</h3><p>${item.body}</p></div>`;
    const next = dialog.querySelector("[data-tour-next]");
    next.innerHTML = current === tourData.length - 1 ? "Finish Tour" : `Next: ${["", "Recommendations", "Borrow / Read", "Student View", "Librarian Intelligence"][current + 1]} <i data-lucide="arrow-right"></i>`;
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
  lucide.createIcons();
});
