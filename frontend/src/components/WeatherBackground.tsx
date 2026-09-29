'use client';

import React from 'react';

interface WeatherBackgroundProps {
  iconKey?: string;
  isDay?: boolean;
}

export default function WeatherBackground({ iconKey, isDay = true }: WeatherBackgroundProps) {
  const isCloudy = iconKey?.includes('cloud') || iconKey?.includes('overcast') || iconKey?.includes('fog');
  const isRainy = iconKey?.includes('rain') || iconKey?.includes('drizzle');
  const isStormy = iconKey?.includes('thunderstorm');
  const isSnowy = iconKey?.includes('snow');
  const isClear = !isCloudy && !isRainy && !isStormy && !isSnowy;

  return (
    <div className="fixed inset-0 pointer-events-none z-[-1] overflow-hidden transition-opacity duration-1000">
      {/* Sun or Moon */}
      {isDay ? (
        // Softened against the neutral backdrop. At full strength the sun read as a
        // saturated yellow blob on grey rather than ambient light behind the page.
        <div className="absolute top-12 left-12 md:top-24 md:left-24 w-32 h-32 md:w-48 md:h-48 bg-gradient-to-br from-amber-50 to-amber-200 rounded-full shadow-[0_0_120px_60px_rgba(253,224,71,0.18)] opacity-50 transition-all duration-1000" />
      ) : (
        <div className="absolute top-12 left-12 md:top-24 md:left-24 w-24 h-24 md:w-32 md:h-32 bg-gradient-to-br from-[#fff] to-slate-200 rounded-full shadow-[0_0_80px_20px_rgba(255,255,255,0.2)] opacity-90 transition-all duration-1000">
          {/* Moon craters for detail */}
          <div className="absolute top-4 right-6 w-4 h-4 bg-black/10 rounded-full"></div>
          <div className="absolute bottom-6 left-8 w-6 h-6 bg-black/10 rounded-full"></div>
          <div className="absolute top-10 left-4 w-3 h-3 bg-black/10 rounded-full"></div>
        </div>
      )}

      {/* Stars (Only at night and when mostly clear) */}
      {!isDay && !isRainy && !isSnowy && (
        // Static. A twinkle animation here re-blurs every glass pane above it.
        <div className="absolute inset-0">
          <div className="absolute top-[10%] left-[20%] w-1 h-1 bg-[#fff]/90 rounded-full" />
          <div className="absolute top-[30%] left-[80%] w-1 h-1 bg-[#fff]/70 rounded-full" />
          <div className="absolute top-[15%] left-[60%] w-1.5 h-1.5 bg-[#fff]/80 rounded-full" />
          <div className="absolute top-[40%] left-[10%] w-1 h-1 bg-[#fff]/60 rounded-full" />
          <div className="absolute top-[5%] left-[90%] w-1.5 h-1.5 bg-[#fff]/70 rounded-full" />
          <div className="absolute top-[25%] left-[40%] w-2 h-2 bg-[#fff]/50 rounded-full" />
        </div>
      )}

      {/* Clouds Layer 1 (Background) */}
      {(isCloudy || isRainy || isStormy || isSnowy) && (
        <div className="absolute top-0 left-0 w-full h-full opacity-60 flex flex-wrap gap-10">
          <div className="absolute top-[-5%] left-[-10%] w-[40%] h-[30%] bg-[#fff]/20 blur-[80px] rounded-full"></div>
          <div className="absolute top-[10%] right-[-5%] w-[50%] h-[40%] bg-[#fff]/20 blur-[100px] rounded-full"></div>
          <div className="absolute top-[30%] left-[20%] w-[60%] h-[30%] bg-[#fff]/10 blur-[90px] rounded-full"></div>
        </div>
      )}

      {/* Clouds Layer 2 (Foreground / Darker for Rain) */}
      {(iconKey?.includes('overcast') || isRainy || isStormy || isSnowy) && (
        <div className="absolute top-0 left-0 w-full h-full opacity-80 mix-blend-multiply">
          <div className="absolute top-[-10%] right-[10%] w-[60%] h-[40%] bg-slate-800/40 blur-[100px] rounded-full"></div>
          <div className="absolute top-[20%] left-[-10%] w-[70%] h-[50%] bg-slate-900/40 blur-[120px] rounded-full"></div>
        </div>
      )}

      {/*
        Precipitation and lightning overlays are intentionally absent.

        This whole component is `fixed inset-0` and sits directly behind every
        backdrop-filter glass pane. Anything that animates here forces those panes to
        re-blur their backdrop on every frame, which is what showed up as the cards
        flickering. The rain layer was the worst of it: a 1s infinite scroll, and its
        4px-wide SVG was being stretched to 100px, so each 1px streak rendered as a 25px
        grey block rather than rain. The lightning layer flashed the full viewport white
        on a 7s loop, which is flicker by definition.

        Conditions are already conveyed by the weather icon, the condition text and the
        precipitation figure. If an animated overlay is wanted back, it has to render
        ABOVE the content with its own compositor layer, never in the panes' backdrop.
      */}
    </div>
  );
}
