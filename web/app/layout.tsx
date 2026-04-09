import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "scheMAGIC - Datasheet to KiCad Symbol Generator",
  description:
    "Generate KiCad symbols and footprints from any manufacturer datasheet. Enter a part number, get a production-ready component.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
