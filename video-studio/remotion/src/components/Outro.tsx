// Closing call-to-action card. Scales in, holds, and a pulsing accent ring
// keeps the energy up to the last frame.
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
  cta: string;
  accent: string;
  logo: string | null;
};

export const Outro: React.FC<Props> = ({ cta, accent, logo }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: SNAPPY });
  const pulse = 1 + 0.04 * Math.sin((frame / fps) * Math.PI * 3);

  return (
    <AbsoluteFill
      style={{
        background: backdropGradient(accent),
        fontFamily: FONT_STACK,
        justifyContent: "center",
        alignItems: "center",
        padding: "0 10%",
        textAlign: "center",
      }}
    >
      <div
        style={{
          transform: `scale(${enter * pulse})`,
          opacity: enter,
        }}
      >
        <div
          style={{
            width: 132,
            height: 132,
            borderRadius: "50%",
            border: `6px solid ${accent}`,
            margin: "0 auto 44px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {logo ? (
            <Img src={staticFile(logo)} style={{ height: 64 }} />
          ) : (
            <span style={{ fontSize: 60 }}>{"▶"}</span>
          )}
        </div>

        <h1
          style={{
            margin: 0,
            fontSize: 72,
            fontWeight: 800,
            color: COLORS.white,
          }}
        >
          {cta}
        </h1>
      </div>

      <div
        style={{
          position: "absolute",
          bottom: 90,
          fontSize: 30,
          fontWeight: 600,
          color: accent,
          opacity: interpolate(frame, [10, 25], [0, 1], {
            extrapolateRight: "clamp",
          }),
        }}
      >
        Xalq Insurance Digital OS
      </div>
    </AbsoluteFill>
  );
};
