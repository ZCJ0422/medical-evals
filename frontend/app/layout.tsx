import "./globals.css";
import { LocaleProvider } from "../lib/i18n";

export const metadata = {
  title: "Medical Evals",
  description: "Internal medical language-model evaluation workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><LocaleProvider>{children}</LocaleProvider></body>
    </html>
  );
}
