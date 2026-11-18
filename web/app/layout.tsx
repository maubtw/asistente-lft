import type { Metadata } from "next";
import { Instrument_Sans, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// "La voz de la ley": título, respuesta y texto de los artículos.
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin", "latin-ext"],
  axes: ["opsz"],
  style: ["normal", "italic"],
});

// Toda la interfaz.
const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin", "latin-ext"],
});

export const metadata: Metadata = {
  title: "Asistente LFT",
  description:
    "Pregúntale a la Ley Federal del Trabajo y lee el artículo exacto que sustenta cada respuesta.",
};

// Tipo explícito: `LayoutProps` lo genera Next al correr dev/build y no existe en un clon limpio.
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className={`${sourceSerif.variable} ${instrumentSans.variable} antialiased`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
