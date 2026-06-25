// Opening title card: an accent bar wipes in, the title rises, the subtitle
// follows a few frames later.
import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { backdropGradient, COLORS, FONT_STACK, SNAPPY } from "../theme";

type Props = {
  title: string;
  subtitle: string;
  accent: string;
  logo: string | null;
};

export const Intro: React.FC<Props> = ({ title, subtitle, accent, logo }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  const titleIn = spring({ frame, fps, config: SNAPPY });
  const subIn = spring({ frame: frame - 8, fps, config: SNAPPY });
  const barWidth = interpolate(titleIn, [0, 1], [0, width * 0.22]);

  return (
    <AbsoluteFill
      style={{
        background: backdropGradient(accent),
        fontFamily: FONT_STACK,
        justifyContent: "center",
        alignItems: "center",
        padding: "0 8%",
        textAlign: "center",
      }}
    >
      {logo && (
        <Img
          src={staticFile(logo)}
          style={{ height: 64, marginBottom: 40, opacity: titleIn }}
        />
      )}

      <div
        style={{
          height: 8,
          width: barWidth,
          backgroundColor: accent,
          borderRadius: 4,
          marginBottom: 36,
        }}
      />

      <h1
        style={{
          margin: 0,
          fontSize: 86,
          lineHeight: 1.08,
          fontWeight: 800,
          color: COLORS.white,
          opacity: titleIn,
          transform: `translateY(${interpolate(titleIn, [0, 1], [40, 0])}px)`,
        }}
      >
        {title}
      </h1>

      <p
        style={{
          marginTop: 28,
          fontSize: 38,
          fontWeight: 500,
          color: COLORS.muted,
          opacity: subIn,
          transform: `translateY(${interpolate(subIn, [0, 1], [24, 0])}px)`,
        }}
      >
        {subtitle}
      </p>
    </AbsoluteFill>
  );
};
