// Shared visual language for every motion-graphics layer.

export const FONT_STACK =
  "'Segoe UI', 'Inter', system-ui, -apple-system, sans-serif";

export const COLORS = {
  ink: "#0A0E14", // near-black background
  inkSoft: "#141A24", // raised surface
  white: "#FFFFFF",
  muted: "rgba(255,255,255,0.72)",
};

// A dark, slightly cinematic backdrop used by the intro and outro cards.
export const backdropGradient = (accent: string): string =>
  `radial-gradient(120% 120% at 50% 0%, ${accent}22 0%, ${COLORS.ink} 60%)`;

// Spring config tuned for snappy, energetic motion (matches the music brief).
export const SNAPPY = { damping: 14, mass: 0.6, stiffness: 120 };
