import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'WeatherGPT — AI Weather Intelligence & Disaster Awareness Platform',
  description:
    'Next-generation meteorological intelligence, hyper-local forecasts, and official disaster safety advisories powered by Google Gemini and Open-Meteo.',
  keywords: ['weather', 'forecast', 'ai weather', 'climate', 'disaster alerts', 'gemini', 'open-meteo'],
  authors: [{ name: 'WeatherGPT Team' }],
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🌤️</text></svg>',
  },
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
