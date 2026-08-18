import type { Metadata } from "next";
import { AppShell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "SentinelAlpha — Autonomous Trading Control Plane",
  description: "Explainable, risk-aware supervision for autonomous paper-trading agents.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppShell>{children}</AppShell></body></html>;
}
