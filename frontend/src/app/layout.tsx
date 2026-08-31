import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'WeatherGPT — AI Weather Intelligence & Disaster Awareness Platform',
  description:
    'Next-generation meteorological intelligence, hyper-local forecasts, and official disaster safety advisories powered by Google Gemini and Open-Meteo.',
  keywords: ['weather', 'forecast', 'ai weather', 'climate', 'disaster alerts', 'gemini', 'open-meteo'],
  authors: [{ name: 'WeatherGPT Team' }],
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0f172a',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen font-sans selection:bg-sky-500 selection:text-white">
        {children}
      </body>
    </html>
  );
}
