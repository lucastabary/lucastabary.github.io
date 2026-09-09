/* Site behaviour: theme toggle, blog filtering, per-post table of contents. */
(function () {
  "use strict";

  /* --- theme ------------------------------------------------------------ */

  var root = document.documentElement;

  function currentTheme() {
    var set = root.getAttribute("data-theme");
    if (set === "dark" || set === "light") return set;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
      toggle.setAttribute("aria-label", "Switch to " + (next === "dark" ? "light" : "dark") + " theme");
    });
  }

  /* --- blog list filtering ---------------------------------------------- */

  var list = document.querySelector("[data-post-list]");
  if (list) {
    var cards = Array.prototype.slice.call(list.querySelectorAll(".post-card"));
    var search = document.querySelector("[data-search]");
    var tagButtons = Array.prototype.slice.call(document.querySelectorAll(".tag-filter"));
    var noResults = document.querySelector("[data-no-results]");
    var activeTag = "";

    function apply() {
      var query = (search && search.value || "").trim().toLowerCase();
      var visible = 0;

      cards.forEach(function (card) {
        var tags = (card.dataset.tags || "").split("|").filter(Boolean);
        var haystack = ((card.textContent || "") + " " + (card.dataset.text || "")).toLowerCase();
        var matchesTag = !activeTag || tags.indexOf(activeTag) !== -1;
        var matchesText = !query || haystack.indexOf(query) !== -1;
        var show = matchesTag && matchesText;
        card.hidden = !show;
        if (show) visible++;
      });

      if (noResults) noResults.hidden = visible !== 0;
    }

    if (search) search.addEventListener("input", apply);

    tagButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        activeTag = button.dataset.tag === activeTag ? "" : (button.dataset.tag || "");
        tagButtons.forEach(function (other) {
          other.classList.toggle("is-active", (other.dataset.tag || "") === activeTag);
        });
        apply();
      });
    });

    apply();
  }

  /* --- table of contents ------------------------------------------------- */

  var body = document.querySelector("[data-post-body]");
  var toc = document.querySelector("[data-toc]");
  var tocList = document.querySelector("[data-toc-list]");

  if (body && toc && tocList) {
    var headings = Array.prototype.slice.call(body.querySelectorAll("h2, h3"));

    if (headings.length >= 3) {
      var used = Object.create(null);

      headings.forEach(function (heading) {
        if (!heading.id) {
          var base = (heading.textContent || "section")
            .toLowerCase().replace(/[^\w\s-]/g, "").trim().replace(/[\s_-]+/g, "-") || "section";
          var id = base;
          var n = 2;
          while (used[id] || document.getElementById(id)) { id = base + "-" + n++; }
          heading.id = id;
        }
        used[heading.id] = true;

        var link = document.createElement("a");
        link.href = "#" + heading.id;
        link.textContent = (heading.textContent || "").replace(/[#¶]\s*$/, "").trim();
        link.className = heading.tagName === "H3" ? "level-3" : "level-2";
        tocList.appendChild(link);
      });

      toc.hidden = false;

      var links = Array.prototype.slice.call(tocList.querySelectorAll("a"));
      if ("IntersectionObserver" in window) {
        var seen = new Map();
        var observer = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) { seen.set(entry.target.id, entry.isIntersecting); });
          var currentId = null;
          headings.forEach(function (heading) {
            if (seen.get(heading.id) && !currentId) currentId = heading.id;
          });
          links.forEach(function (link) {
            link.classList.toggle("is-current", link.hash === "#" + currentId);
          });
        }, { rootMargin: "-72px 0px -70% 0px" });
        headings.forEach(function (heading) { observer.observe(heading); });
      }
    }
  }
})();
