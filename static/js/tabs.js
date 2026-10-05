/* Progressive enhancement for the book detail tab strip.
 *
 * Every panel is rendered and visible in the HTML, so the page is complete
 * without JavaScript. This file only hides the inactive panels and wires the
 * buttons, and it marks the container ready so the CSS knows it is safe to
 * hide anything.
 */
document.addEventListener("DOMContentLoaded", () => {
  const panels = document.querySelector("[data-tab-panels]");
  if (!panels) return;

  const buttons = [...document.querySelectorAll("[data-tab]")];
  const sections = [...panels.querySelectorAll("[data-panel]")];
  if (!buttons.length || buttons.length !== sections.length) return;

  const select = (name, { focus = false } = {}) => {
    buttons.forEach((button) => {
      const on = button.dataset.tab === name;
      button.classList.toggle("active", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      // Roving tabindex keeps the tab strip a single tab stop.
      button.tabIndex = on ? 0 : -1;
      if (on && focus) button.focus();
    });
    sections.forEach((section) => {
      section.classList.toggle("is-active", section.dataset.panel === name);
    });
    panels.dataset.active = name;
  };

  buttons.forEach((button, index) => {
    button.addEventListener("click", () => select(button.dataset.tab));

    // Left/right arrows move between tabs, as expected of a tablist.
    button.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const next = (index + step + buttons.length) % buttons.length;
      select(buttons[next].dataset.tab, { focus: true });
    });
  });

  // "Digital material available" and the post-review redirect both point at a
  // panel by hash. Honour that instead of leaving the link inert.
  const openFromHash = () => {
    const wanted = (window.location.hash || "").replace("#panel-", "");
    if (wanted && sections.some((s) => s.dataset.panel === wanted)) {
      select(wanted);
    }
  };
  document.querySelectorAll("[data-tab-open]").forEach((link) => {
    link.addEventListener("click", () => select(link.dataset.tabOpen));
  });
  window.addEventListener("hashchange", openFromHash);

  // Only now is it safe to hide the panels that are not selected.
  panels.classList.add("is-ready");
  openFromHash();
});
