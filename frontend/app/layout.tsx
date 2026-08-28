import "./globals.css";
import { LocaleProvider } from "../lib/i18n";

export const metadata = {
  title: "Medical Evals · 医疗大模型评测",
  description: "公开、可复现的医疗大模型评测数据与榜单。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body><LocaleProvider>{children}</LocaleProvider></body>
    </html>
  );
}
