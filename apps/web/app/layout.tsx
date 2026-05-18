import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "DeevAI — Weekly bid agent for Google DV360",
    template: "%s · DeevAI",
  },
  description:
    "DeevAI reads what happened on your Google DV360 campaigns, decides what to adjust, and asks you to approve before applying. Every Monday.",
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
  ),
  openGraph: {
    title: "DeevAI",
    description: "The weekly bid agent for Google DV360.",
    type: "website",
  },
  robots: {
    // While in private beta, keep search engines out
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
