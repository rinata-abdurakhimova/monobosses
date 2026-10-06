import type { Metadata } from "next";
import { WorkspaceShell } from "@/components/WorkspaceShell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Committee · Biotech underwriting", template: "%s · Committee" },
  description: "A synthetic frontend preview of a virtual biotech investment committee.",
  robots: { index: false, follow: false },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><WorkspaceShell>{children}</WorkspaceShell></body></html>;
}
