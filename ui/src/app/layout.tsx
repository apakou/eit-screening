import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Présélection MEST",
  description: "Verdicts proposés et validation par les évaluateurs",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <header className="border-b">
          <div className="mx-auto flex max-w-7xl items-baseline justify-between gap-4 px-4 py-3">
            <Link href="/" className="font-semibold">
              Présélection MEST AI Startup Program
            </Link>
            <p className="text-sm text-muted-foreground">
              Le système propose, l&apos;évaluateur décide.
            </p>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
