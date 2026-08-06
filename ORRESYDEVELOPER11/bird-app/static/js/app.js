function normalize(value) {
  return (value || "").toString().trim().toLowerCase();
}

function debounce(fn, ms) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

function showToast(message, type, duration) {
  type = type || "info";
  duration = duration || 4000;
  const container = document.getElementById("toast-container");
  if (!container) return;
  const icons = { info: "check-circle", error: "triangle-alert", warning: "alert-triangle" };
  const icon = icons[type] || "check-circle";
  const toast = document.createElement("div");
  toast.className = "toast toast-" + type;
  toast.innerHTML = '<i data-lucide="' + icon + '"></i><span>' + message + "</span>";
  container.appendChild(toast);
  if (window.lucide) window.lucide.createIcons({ icons: { [icon]: true }, attrs: { "aria-hidden": "true" } });
  const remove = () => {
    toast.classList.add("removing");
    setTimeout(() => toast.remove(), 300);
  };
  setTimeout(remove, duration);
  toast.addEventListener("click", remove);
}

function updateFilterCount() {
  document.querySelectorAll("[data-filter-grid], [data-park-grid]").forEach((grid) => {
    const visible = Array.from(grid.children).filter((c) => !c.hidden && c.matches("article")).length;
    const total = Array.from(grid.children).filter((c) => c.matches("article")).length;
    const badge = grid.parentElement.querySelector(".filter-count");
    if (badge) badge.textContent = visible + " / " + total;
  });
}

function applySpeciesFilters() {
  const search = normalize(document.querySelector("[data-filter-search]")?.value);
  const habitat = normalize(document.querySelector('[data-filter-select="habitat"]')?.value);
  const status = normalize(document.querySelector('[data-filter-select="status"]')?.value);

  document.querySelectorAll("[data-filter-grid] .species-card").forEach((card) => {
    const matchesSearch = normalize(card.dataset.name).includes(search);
    const matchesHabitat = !habitat || normalize(card.dataset.habitat) === habitat;
    const matchesStatus = !status || normalize(card.dataset.status) === status;
    card.hidden = !(matchesSearch && matchesHabitat && matchesStatus);
  });
  updateFilterCount();
}

function applyParkFilters() {
  const region = normalize(document.querySelector('[data-park-select="region"]')?.value);
  const habitat = normalize(document.querySelector('[data-park-select="habitat"]')?.value);

  document.querySelectorAll("[data-park-grid] .park-card").forEach((card) => {
    const matchesRegion = !region || normalize(card.dataset.region) === region;
    const matchesHabitat = !habitat || normalize(card.dataset.habitat) === habitat;
    card.hidden = !(matchesRegion && matchesHabitat);
  });
  updateFilterCount();
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons({ strokeWidth: 1.8 });
  } else {
    const fallback = {
      feather: '<path d="M20 4c-6 0-12 5-14 13l-2 3 3-2c8-2 13-8 13-14z"/><path d="M4 20c4-5 8-9 14-14"/>',
      menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
      x: '<path d="M18 6 6 18M6 6l12 12"/>',
      search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
      "scan-search": '<path d="M7 3H5a2 2 0 0 0-2 2v2M17 3h2a2 2 0 0 1 2 2v2M7 21H5a2 2 0 0 1-2-2v-2M17 21h2a2 2 0 0 0 2-2v-2"/><circle cx="11" cy="11" r="4"/><path d="m16 16-2-2"/>',
      "triangle-alert": '<path d="M12 3 2 21h20L12 3z"/><path d="M12 9v5M12 17h.01"/>',
      "image-up": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m8 13 2.5-2.5L14 14l2-2 3 3"/><path d="M12 3v8M9 6l3-3 3 3"/>',
      cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3"/>',
      map: '<path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3V6z"/><path d="M9 3v15M15 6v15"/>',
      trees: '<path d="M8 19V9M16 19V7"/><path d="M4 13l4-8 4 8H4zM12 12l4-9 4 9h-8z"/>',
      waves: '<path d="M3 8c3-2 5 2 8 0s5 2 10 0M3 14c3-2 5 2 8 0s5 2 10 0M3 20c3-2 5 2 8 0s5 2 10 0"/>',
      wheat: '<path d="M12 22V4M8 8l4 4 4-4M7 13l5 5 5-5M6 18l6 4 6-4"/>',
      mountain: '<path d="M3 20h18L14 6l-4 8-2-4-5 10z"/>',
      shell: '<path d="M4 20c0-8 4-14 8-14s8 6 8 14H4z"/><path d="M12 6v14M7 9l5 11M17 9l-5 11"/>',
      thermometer: '<path d="M14 14.8V5a4 4 0 0 0-8 0v9.8A5 5 0 1 0 14 14.8z"/>',
      leaf: '<path d="M20 4c-9 1-15 6-15 13 0 2 2 4 4 4 7 0 12-8 11-17z"/><path d="M5 19c4-5 8-8 14-13"/>',
      "map-pin": '<path d="M12 21s7-5 7-12a7 7 0 1 0-14 0c0 7 7 12 7 12z"/><circle cx="12" cy="9" r="2"/>',
      route: '<circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/><path d="M7 19h4a3 3 0 0 0 0-6h2a3 3 0 0 0 0-6h4"/>',
      "shield-check": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-5"/>',
      "calendar-days": '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18M8 14h.01M12 14h.01M16 14h.01"/>',
      ruler: '<path d="M4 17 17 4l3 3L7 20l-3-3z"/><path d="m12 9 3 3M9 12l2 2M15 6l2 2"/>',
      "globe-2": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
      bookmark: '<path d="M6 3h12v18l-6-4-6 4V3z"/>',
      "layout-dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
      "log-in": '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="m10 17 5-5-5-5M15 12H3"/>',
      "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
      "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
      "cloud-sun": '<path d="M12 2v3M5.6 5.6l2.1 2.1M2 12h3"/><path d="M18 18.5A4.5 4.5 0 0 0 13.5 14H13a6 6 0 1 0-9 5.2"/><path d="M8 19h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.6 1.8"/>',
      navigation: '<path d="m12 2 7 20-7-4-7 4 7-20z"/>',
      ticket: '<path d="M3 8a2 2 0 0 1 2-2h14v4a2 2 0 0 0 0 4v4H5a2 2 0 0 1-2-2v-4a2 2 0 0 0 0-4V8z"/><path d="M13 6v12"/>',
      "moon": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
      "sun": '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>',
      "maximize-2": '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
      "flag": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
      "alert-triangle": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    };

    document.querySelectorAll("[data-lucide]").forEach((icon) => {
      const name = icon.getAttribute("data-lucide");
      icon.outerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${fallback[name] || fallback.leaf}</svg>`;
    });
  }

  const debouncedSpeciesFilter = debounce(applySpeciesFilters, 150);
  document.querySelectorAll("[data-filter-search], [data-filter-select]").forEach((control) => {
    control.addEventListener("input", debouncedSpeciesFilter);
    control.addEventListener("change", applySpeciesFilters);
  });

  document.querySelectorAll("[data-park-select]").forEach((control) => {
    control.addEventListener("change", applyParkFilters);
  });

  initWeatherCards();
  initMiniMaps();
  initTanzaniaMap();
  initAdminFilters();
  initSideNavigation();
  initDarkMode();
  initSightingHeatmap();
  initScrollReveal();
  initLazyImages();
  initFilterCountBadges();
  applySpeciesFilters();
  applyParkFilters();
});

function initSideNavigation() {
  const openButton = document.querySelector("[data-nav-open]");
  const closeButton = document.querySelector("[data-nav-close]");
  const nav = document.querySelector("[data-side-nav]");
  const overlay = document.querySelector("[data-nav-overlay]");
  if (!openButton || !closeButton || !nav || !overlay) return;

  const open = () => {
    overlay.hidden = false;
    nav.classList.add("is-open");
    nav.setAttribute("aria-hidden", "false");
    openButton.setAttribute("aria-expanded", "true");
    document.body.classList.add("nav-open");
    closeButton.focus();
  };

  const close = () => {
    nav.classList.remove("is-open");
    nav.setAttribute("aria-hidden", "true");
    openButton.setAttribute("aria-expanded", "false");
    document.body.classList.remove("nav-open");
    window.setTimeout(() => {
      overlay.hidden = true;
    }, 180);
  };

  openButton.addEventListener("click", open);
  closeButton.addEventListener("click", close);
  overlay.addEventListener("click", close);
  nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", close));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.classList.contains("is-open")) {
      close();
      openButton.focus();
    }
  });
}

function initAdminFilters() {
  const input = document.querySelector("[data-admin-search]");
  if (!input) return;

  const apply = () => {
    const query = normalize(input.value);
    document.querySelectorAll("[data-admin-item], [data-admin-prediction]").forEach((item) => {
      const text = normalize(item.dataset.adminItem || item.dataset.adminPrediction);
      item.hidden = query && !text.includes(query);
    });
  };

  input.addEventListener("input", apply);
}

function initWeatherCards() {
  document.querySelectorAll("[data-weather-card]").forEach((card) => {
    const lat = card.dataset.lat;
    const lon = card.dataset.lon;
    const target = card.querySelector("strong");
    fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current_weather=true&timezone=auto`)
      .then((response) => response.json())
      .then((data) => {
        const current = data.current_weather;
        target.textContent = current ? `${Math.round(current.temperature)} C, wind ${Math.round(current.windspeed)} km/h` : "Weather unavailable";
      })
      .catch(() => {
        target.textContent = "Weather unavailable offline";
      });
  });
}

function initMiniMaps() {
  document.querySelectorAll("[data-mini-map]").forEach((el) => {
    if (!window.L) return;
    const lat = Number(el.dataset.lat);
    const lon = Number(el.dataset.lon);
    const map = L.map(el, { scrollWheelZoom: false }).setView([lat, lon], 8);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    L.marker([lat, lon], { title: el.dataset.title }).addTo(map).bindPopup(el.dataset.title);
  });
}

function distanceKm(a, b) {
  const earth = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * earth * Math.asin(Math.sqrt(x));
}

function initTanzaniaMap() {
  const el = document.getElementById("tanzania-map");
  if (!el || !window.L) return;

  const map = L.map(el).setView([-6.2, 35.3], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const layer = L.layerGroup().addTo(map);
  let parks = [];

  const controls = {
    search: document.querySelector("[data-map-search]"),
    region: document.querySelector("[data-map-region]"),
    habitat: document.querySelector("[data-map-habitat]"),
    bird: document.querySelector("[data-map-bird]"),
  };

  function render() {
    layer.clearLayers();
    const query = normalize(controls.search?.value);
    const region = normalize(controls.region?.value);
    const habitat = normalize(controls.habitat?.value);
    const bird = normalize(controls.bird?.value);

    parks.forEach((park) => {
      const haystack = normalize(`${park.name} ${park.region} ${park.habitat_type} ${(park.birds || []).join(" ")}`);
      const matches = (!query || haystack.includes(query))
        && (!region || normalize(park.region).includes(region))
        && (!habitat || normalize(park.habitat_type) === habitat)
        && (!bird || normalize((park.birds || []).join(" ")).includes(bird));
      if (!matches) return;

      L.marker([park.latitude, park.longitude], { title: park.name })
        .addTo(layer)
        .bindPopup(`<strong>${park.name}</strong><br>${park.region}<br>${park.habitat_type}<br><a href="/parks/${park.id}">Open details</a>`);
    });
  }

  fetch("/api/map-data")
    .then((response) => response.json())
    .then((data) => {
      parks = data.parks || [];
      render();
    });

  Object.values(controls).forEach((control) => {
    control?.addEventListener("input", render);
    control?.addEventListener("change", render);
  });

  document.querySelector("[data-find-nearby]")?.addEventListener("click", () => {
    const panel = document.querySelector("[data-nearby-panel]");
    if (!navigator.geolocation) {
      panel.innerHTML = "<strong>Nearby places</strong><p>Location is not supported on this device.</p>";
      return;
    }
    navigator.geolocation.getCurrentPosition((position) => {
      const here = { lat: position.coords.latitude, lon: position.coords.longitude };
      const nearest = parks
        .map((park) => ({ ...park, distance: distanceKm(here, { lat: park.latitude, lon: park.longitude }) }))
        .sort((a, b) => a.distance - b.distance)
        .slice(0, 5);
      panel.innerHTML = `<strong>Nearby places</strong>${nearest.map((park) => `<a href="/parks/${park.id}">${park.name}<span>${Math.round(park.distance)} km away</span></a>`).join("")}`;
    }, () => {
      panel.innerHTML = "<strong>Nearby places</strong><p>Location permission was not granted.</p>";
    });
  });
}

function initDarkMode() {
  const btn = document.querySelector("[data-dark-toggle]");
  if (!btn) return;

  const saved = localStorage.getItem("theme");
  if (saved === "dark") document.documentElement.classList.add("dark");

  btn.addEventListener("click", () => {
    const isDark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("theme", isDark ? "dark" : "light");
  });

  const fieldBtn = document.querySelector("[data-field-toggle]");
  if (fieldBtn) {
    if (localStorage.getItem("fieldMode") === "on") document.body.classList.add("field-mode");
    fieldBtn.addEventListener("click", () => {
      const on = document.body.classList.toggle("field-mode");
      localStorage.setItem("fieldMode", on ? "on" : "off");
    });
  }
}

function initSightingHeatmap() {
  const map = document.querySelector("#tanzania-map");
  if (!map || !window.L || !window.L.heat) return;

  const toggle = document.querySelector("[data-heatmap-toggle]");
  const species = document.querySelector("[data-heatmap-species]");
  const days = document.querySelector("[data-heatmap-days]");
  if (!toggle) return;

  let heatLayer = null;

  function loadHeatmap() {
    const params = new URLSearchParams();
    if (species && species.value) params.set("bird_id", "");
    if (days && days.value) params.set("days", days.value);

    const url = `/api/sightings?${params.toString()}`;
    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (heatLayer) map.removeLayer(heatLayer);
        if (!toggle.checked) return;

        const points = (data.features || [])
          .filter((f) => f.geometry && f.geometry.coordinates)
          .map((f) => {
            const coords = f.geometry.coordinates;
            const conf = f.properties.confidence || 50;
            return [coords[1], coords[0], conf / 100];
          });

        if (points.length === 0) return;
        heatLayer = L.heatLayer(points, {
          radius: 25,
          blur: 15,
          maxZoom: 10,
          max: 1,
          gradient: { 0.4: "blue", 0.6: "lime", 0.8: "yellow", 1.0: "red" },
        }).addTo(map);
      })
      .catch(() => {});
  }

  toggle.addEventListener("change", loadHeatmap);
  species?.addEventListener("change", loadHeatmap);
  days?.addEventListener("change", loadHeatmap);

  // Initial load after map data is fetched
  const origFetch = window.fetch;
  setTimeout(loadHeatmap, 2000);
}

function initScrollReveal() {
  if (!("IntersectionObserver" in window)) {
    document.querySelectorAll(".reveal").forEach((el) => el.classList.add("visible"));
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
  );
  document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
}

function initLazyImages() {
  if (!("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const img = entry.target;
          img.classList.remove("lqip");
          img.classList.add("lqip-loaded");
          observer.unobserve(img);
        }
      });
    },
    { threshold: 0.05 }
  );
  document.querySelectorAll("img[loading='lazy']").forEach((img) => {
    img.classList.add("lqip");
    observer.observe(img);
    img.addEventListener("load", () => {
      img.classList.remove("lqip");
      img.classList.add("lqip-loaded");
    });
    if (img.complete) {
      img.classList.remove("lqip");
      img.classList.add("lqip-loaded");
    }
  });
}

function initFilterCountBadges() {
  document.querySelectorAll("[data-filter-grid], [data-park-grid]").forEach((grid) => {
    const parent = grid.parentElement;
    if (parent && !parent.querySelector(".filter-count")) {
      const badge = document.createElement("span");
      badge.className = "filter-count";
      grid.parentNode.insertBefore(badge, grid.nextSibling);
    }
  });
}
