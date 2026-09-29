import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'WeatherGPT — AI Weather Intelligence & Disaster Awareness Platform',
  description:
    'Next-generation meteorological intelligence, hyper-local forecasts, and official disaster safety advisories powered by Google Gemini and Open-Meteo.',
  keywords: ['weather', 'forecast', 'ai weather', 'climate', 'disaster alerts', 'gemini', 'open-meteo'],
  authors: [{ name: 'WeatherGPT Team' }],
  manifest: '/manifest.json',
  applicationName: 'WeatherGPT',
  appleWebApp: {
    capable: true,
    title: 'WeatherGPT',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: [
      { url: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/icon-192.png', sizes: '192x192', type: 'image/png' }],
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#18181b',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-zinc-950 text-ink min-h-screen font-sans selection:bg-sky-500 selection:text-[#fff]">
        {children}
      </body>
    </html>
  );
}
