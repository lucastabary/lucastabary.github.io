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
    // The label (and hover tooltip) names the theme a click switches to.
    var label = function () {
      var text = "Switch to " + (currentTheme() === "dark" ? "light" : "dark") + " theme";
      toggle.setAttribute("aria-label", text);
      toggle.setAttribute("title", text);
    };
    label();
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
      label();
    });
  }

  /* --- blog list filtering ---------------------------------------------- */

  // Posts arrive newest first from the build; filters only hide cards, so the
  // order is always preserved. Project, folder and tag combine (AND) and are
  // mirrored in the query string, so a filtered view can be linked to.
  var list = document.querySelector("[data-post-list]");
  if (list) {
    var cards = Array.prototype.slice.call(list.querySelectorAll(".post-card"));
    var search = document.querySelector("[data-search]");
    var noResults = document.querySelector("[data-no-results]");
    var status = document.querySelector("[data-filter-status]");
    var kinds = ["project", "folder", "tag"];
    var active = { project: "", folder: "", tag: "" };

    var chips = {};
    kinds.forEach(function (kind) {
      chips[kind] = Array.prototype.slice.call(
        document.querySelectorAll(".chip[data-" + kind + "]"));
    });

    function matches(card, kind) {
      var value = active[kind];
      if (!value) return true;
      if (kind === "tag") return (card.dataset.tags || "").split("|").indexOf(value) !== -1;
      return (card.dataset[kind] || "") === value;
    }

    function syncChips() {
      kinds.forEach(function (kind) {
        chips[kind].forEach(function (chip) {
          chip.classList.toggle("is-active", (chip.dataset[kind] || "") === active[kind]);
          chip.setAttribute("aria-pressed", chip.classList.contains("is-active") ? "true" : "false");
        });
      });
      // Only offer the folders of the selected project.
      chips.folder.forEach(function (chip) {
        var owner = chip.dataset.folderProject;
        chip.hidden = !!(owner && active.project && owner !== active.project);
      });
    }

    function syncUrl() {
      if (!window.history || !history.replaceState) return;
      var params = new URLSearchParams(window.location.search);
      kinds.forEach(function (kind) {
        if (active[kind]) params.set(kind, active[kind]); else params.delete(kind);
      });
      var query = params.toString();
      history.replaceState(null, "", window.location.pathname + (query ? "?" + query : "") + window.location.hash);
    }

    function apply() {
      var query = (search && search.value || "").trim().toLowerCase();
      var visible = 0;

      cards.forEach(function (card) {
        var haystack = ((card.textContent || "") + " " + (card.dataset.text || "")).toLowerCase();
        var show = kinds.every(function (kind) { return matches(card, kind); })
          && (!query || haystack.indexOf(query) !== -1);
        card.hidden = !show;
        if (show) visible++;
      });

      syncChips();
      if (noResults) noResults.hidden = visible !== 0;
      if (status) {
        var filtered = visible !== cards.length;
        status.textContent = filtered ? visible + " of " + cards.length + " posts" : "";
        status.hidden = !filtered;
      }
    }

    if (search) search.addEventListener("input", apply);

    kinds.forEach(function (kind) {
      chips[kind].forEach(function (chip) {
        chip.addEventListener("click", function () {
          var value = chip.dataset[kind] || "";
          // Clicking the active chip clears that filter.
          active[kind] = value === active[kind] ? "" : value;
          // A folder belongs to one project: picking it pins that project too,
          // and switching project drops a folder that is not in it.
          if (kind === "folder" && active.folder) {
            var owner = chip.dataset.folderProject || "";
            if (owner && chips.project.length) active.project = owner;
          }
          if (kind === "project" && active.folder) {
            var current = chips.folder.filter(function (c) { return c.dataset.folder === active.folder; })[0];
            if (current && active.project && current.dataset.folderProject !== active.project) active.folder = "";
          }
          apply();
          syncUrl();
        });
      });
    });

    // Restore filters from the URL (/blog/?project=nirs-spectroscopy).
    var initial = new URLSearchParams(window.location.search);
    kinds.forEach(function (kind) {
      var value = initial.get(kind);
      if (value && chips[kind].some(function (c) { return c.dataset[kind] === value; })) {
        active[kind] = value;
      }
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
