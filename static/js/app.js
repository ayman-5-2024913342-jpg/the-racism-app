(() => {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.querySelector("#main-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const isOpen = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && nav.classList.contains("open")) {
        nav.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  }

  // HTMX error surface: show server messages (JSON {detail}) in the flash region instead of failing silently.
  const flash = document.getElementById("flash");
  function show(message) {
    if (!flash) return;
    const box = document.createElement("div");
    box.className = "flash error";
    box.textContent = message;
    flash.replaceChildren(box);
    window.setTimeout(() => box.remove(), 8000);
  }
  document.body.addEventListener("htmx:responseError", (event) => {
    let message = "Something went wrong. Please try again.";
    try { message = JSON.parse(event.detail.xhr.responseText).detail || message; } catch (e) { /* keep default */ }
    show(message);
  });
  document.body.addEventListener("htmx:sendError", () => show("Couldn't reach the server. Check your connection and try again."));
})();
