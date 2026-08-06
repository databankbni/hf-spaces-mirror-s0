// Service worker for Extra Time Monitor background 78' alerts.
// Shows an OS notification when a push arrives — but stays silent if a tab is
// already visible, since the open page plays its own Web Audio chime (no double alert).

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

// MIUI/Redmi (and Android/FCM generally) can silently rotate this device's push
// endpoint when the OS kills the service worker. Without re-registering the new
// endpoint the server keeps pushing to a dead one and the device goes quiet — even
// though the user never muted. Re-subscribe and hand the server the new endpoint,
// passing the old one so it can carry the mute flag over and drop the stale record.
self.addEventListener("pushsubscriptionchange", event => {
  event.waitUntil(
    (async () => {
      try {
        const res = await fetch("/api/push/public-key");
        if (!res.ok) return;
        const { publicKey } = await res.json();
        if (!publicKey) return;
        const subscription = await self.registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey)
        });
        const oldEndpoint = event.oldSubscription && event.oldSubscription.endpoint;
        await fetch("/api/push/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subscription, oldEndpoint })
        });
      } catch {
        // Best-effort: the next page open re-registers via enablePushNotifications().
      }
    })()
  );
});

self.addEventListener("push", event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }

  const title = data.title || "Extra Time Monitor";
  const body = data.body || "A match has reached the 78' alert.";
  const tag = data.tag || "extra-time-alert";
  const url = data.url || "/";

  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const hasVisibleTab = clientList.some(c => c.visibilityState === "visible");
      // A visible tab handles its own chime — don't stack an OS notification on top.
      if (hasVisibleTab) return;

      await self.registration.showNotification(title, {
        body,
        tag,
        renotify: true,
        // requireInteraction keeps the alert on screen until tapped — MIUI/Android
        // otherwise auto-dismisses time-sensitive alerts before they're noticed.
        requireInteraction: true,
        icon: "/favicon.svg",
        badge: "/favicon.svg",
        vibrate: [120, 60, 120, 60, 240],
        data: { url }
      });
    })()
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of clientList) {
        if ("focus" in client) {
          client.focus();
          if ("navigate" in client && targetUrl !== "/") client.navigate(targetUrl).catch(() => {});
          return;
        }
      }
      if (self.clients.openWindow) await self.clients.openWindow(targetUrl);
    })()
  );
});
