// Public website measurement only. Never loaded into the local workspace app.
(() => {
  const id = document.currentScript?.dataset.measurementId;
  if (!/^G-[A-Z0-9]+$/.test(id ?? "") || location.hostname !== "loopx-project.github.io" ||
      navigator.doNotTrack === "1" || navigator.globalPrivacyControl || window.__loopxAnalyticsActive) return;
  window.__loopxAnalyticsActive = true;
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  const originOnly = (url) => { try { return new URL(url).origin; } catch { return ""; } };
  let previous = "";
  const pageFields = () => {
    const canonical = document.querySelector('link[rel="canonical"]')?.href;
    if (!canonical) return null;
    const url = new URL(canonical);
    if (url.origin !== "https://loopx-project.github.io" || !url.pathname.startsWith("/loopx/")) return null;
    return { page_location: url.origin + url.pathname, page_referrer: originOnly(document.referrer),
      page_title: document.title, language: new URLSearchParams(location.search).get("lang") === "zh" ? "zh-CN" : document.documentElement.lang };
  };
  const initial = pageFields();
  if (!initial) return;
  gtag("js", new Date());
  gtag("set", initial);
  gtag("config", id, { ...initial, send_page_view: false,
    allow_google_signals: false, allow_ad_personalization_signals: false });
  const pageView = () => {
    const fields = pageFields();
    if (!fields || fields.page_location === previous) return;
    previous = fields.page_location;
    gtag("set", fields);
    gtag("event", "page_view", fields);
  };
  pageView();
  const tag = document.createElement("script");
  tag.async = true;
  tag.src = `https://www.googletagmanager.com/gtag/js?id=${id}`;
  document.head.append(tag);
  // Material's instant navigation updates the canonical element. Locale and
  // fragment changes on a React page must not inflate pageview counts.
  new MutationObserver(pageView).observe(document.head, { subtree: true, childList: true, attributes: true, attributeFilter: ["href"] });
  const event = (name, fields = {}) => {
    const page = pageFields();
    if (page) gtag("event", name, { ...page, ...fields });
  };
  document.addEventListener("click", (e) => {
    const target = e.target instanceof Element ? e.target : null;
    const marked = target?.closest("[data-analytics-event]")?.dataset.analyticsEvent;
    if (["setup_open", "showcase_open"].includes(marked)) event(marked);
    const anchor = target?.closest("a[href]");
    if (!anchor) return;
    const url = new URL(anchor.href);
    if (url.hostname === "github.com" && /^\/(?:loopx-project|huangruiteng)\/loopx(?:\/|$)/.test(url.pathname)) {
      event("github_click", { destination: url.pathname.includes("packages/dsh-loopx-plugin") ? "dsh_plugin" : "repository" });
    } else if (url.origin === location.origin && url.pathname.startsWith("/loopx/docs/") && url.pathname !== location.pathname) {
      event("docs_open");
    }
  });
  window.addEventListener("loopx:setup-copy", (e) => {
    if (e.detail === "agent" || e.detail === "shell") event("setup_copy", { setup_method: e.detail });
  });
})();
