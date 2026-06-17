import type { Metadata } from "next";
import { Newsreader, Inter, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { Nav } from "@/components/Nav";
import { BRAND } from "@/lib/format";

const newsreader = Newsreader({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-serif",
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
});

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: `${BRAND} — property opportunity briefings`,
  description:
    "Written, sourced, confidence-scored findings about specific UK sites.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en-GB"
      className={`${newsreader.variable} ${inter.variable} ${plexMono.variable}`}
    >
      <body>
        <AuthProvider>
          <Nav />
          <main className="mx-auto max-w-wide px-5 sm:px-8 pb-24">
            {children}
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
