import "./globals.css";

export const metadata = {
  title: "DHAAL — your shield against scams",
  description:
    "Paste any suspicious message, screenshot or call — get an explained verdict in seconds. Free, in your language, for every phone.",
  manifest: "/manifest.json",
};

export const viewport = {
  themeColor: "#1f3864",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
