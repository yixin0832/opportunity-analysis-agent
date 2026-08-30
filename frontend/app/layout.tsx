import type { Metadata } from "next";
import { AppHeader } from "@/components/app-header";
import "./globals.css";

export const metadata: Metadata = {
  title: "商机录入与分析助手",
  description: "将销售拜访记录转换为可追溯的商机分析结果。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AppHeader />
        <main>{children}</main>
      </body>
    </html>
  );
}
