// Name/role card that slides in from the left edge, holds, then slides out.
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { COLORS, FONT_STACK, SNAPPY } from "../theme";

type Props = {
  line1: string;
  line2: string;
  accent: string;
  durationInFrames: number;
};

export const LowerThird: React.FC<Props> = ({
  line1,
  line2,
  accent,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: SNAPPY });
  // Exit slide begins 14 frames before the sequence ends.
  const exit = spring({
    frame: frame - (durationInFrames - 14),
    fps,
    config: SNAPPY,
  });

  const offset = interpolate(enter, [0, 1], [-520, 0]) +
    interpolate(exit, [0, 1], [0, -520]);

  return (
    <AbsoluteFill style={{ fontFamily: FONT_STACK }}>
      <div
        style={{
          position: "absolute",
          left: 56,
          bottom: 240,
          transform: `translateX(${offset}px)`,
          display: "flex",
          alignItems: "stretch",
        }}
      >
        <div style={{ width: 8, backgroundColor: accent, borderRadius: 4 }} />
        <div
          style={{
            backgroundColor: COLORS.inkSoft,
            padding: "18px 30px",
            marginLeft: 14,
            borderRadius: 10,
          }}
        >
          <div
            style={{
              fontSize: 44,
              fontWeight: 800,
              color: COLORS.white,
            }}
          >
            {line1}
          </div>
          {line2 && (
            <div
              style={{
                fontSize: 28,
                fontWeight: 500,
                color: accent,
                marginTop: 4,
              }}
            >
              {line2}
            </div>
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};
