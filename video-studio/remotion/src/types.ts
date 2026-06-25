// Shape of public/props.json, written by render.py (build_props).
// This is the TypeScript mirror of the Python edit-spec contract.

export type CaptionWord = {
  text: string;
  start: number; // seconds, relative to the base clip
  end: number;
};

export type FinalProps = {
  width: number;
  height: number;
  fps: number;

  baseVideo: string; // staticFile name in public/, e.g. "base.mp4"
  baseDurationInFrames: number;

  intro: {
    enabled: boolean;
    title: string;
    subtitle: string;
    durationInFrames: number;
  };
  outro: {
    enabled: boolean;
    cta: string;
    durationInFrames: number;
  };
  lowerThirds: Array<{
    atFrame: number; // frame within the base segment
    line1: string;
    line2: string;
    durationInFrames: number;
  }>;
  captions: {
    enabled: boolean;
    style: "karaoke" | "block";
    position: "bottom" | "center" | "top";
    words: CaptionWord[];
  };
  brand: {
    accentColor: string;
    logo: string | null; // staticFile name, or null
  };
};

// Fallback props so the composition still opens in `remotion studio`
// before render.py has written a real props.json.
export const DEFAULT_PROPS: FinalProps = {
  width: 1080,
  height: 1080,
  fps: 30,
  baseVideo: "base.mp4",
  baseDurationInFrames: 150,
  intro: {
    enabled: true,
    title: "Xalq Insurance Digital OS Video Studio",
    subtitle: "Preview - render.py supplies real props",
    durationInFrames: 75,
  },
  outro: {
    enabled: true,
    cta: "Follow for more AI automation",
    durationInFrames: 90,
  },
  lowerThirds: [],
  captions: { enabled: false, style: "karaoke", position: "bottom", words: [] },
  brand: { accentColor: "#00E5FF", logo: null },
};
