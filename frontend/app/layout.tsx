import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { DemoToolbar } from "@/components/DemoToolbar";
import { SessionProvider } from "@/lib/SessionProvider";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Cinema Booking — API demo",
  description:
    "A web client for exercising the Cinema Booking API, including live seat locking.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <SessionProvider>
          <DemoToolbar />
          {/* Phone-width column: the design is a mobile app, and constraining
              the width keeps the demo faithful to the wireframes. */}
          <div className="mx-auto min-h-screen w-full max-w-[430px] bg-background shadow-2xl">
            {children}
          </div>
        </SessionProvider>
      </body>
    </html>
  );
}
