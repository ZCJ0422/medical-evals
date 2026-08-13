import "./globals.css";

export const metadata = {
  title: "Medical Evals",
  description: "Internal medical language-model evaluation workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
