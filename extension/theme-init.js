(function () {
  try {
    var saved = localStorage.getItem("glossbook_theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    }
  } catch (_) {}
})();
