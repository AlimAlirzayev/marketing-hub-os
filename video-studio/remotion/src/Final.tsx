// The master composition: intro card -> base video (with captions and
// lower-thirds) -> outro card, laid out on one timeline.
import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  staticFile,
} from "remotion";
import { Captions } from "./components/Captions";
import { Intro } from "./components/Intro";
import { LowerThird } from "./components/LowerThird";
import { Outro } from "./components/Outro";
import { COLORS } from "./theme";
import { FinalProps } from "./types";

export const Final: React.FC<FinalProps> = (props) => {
  const { intro, outro, baseDurationInFrames, captions, lowerThirds, brand } =
    props;

  const introFrames = intro.enabled ? intro.durationInFrames : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.ink }}>
      {/* 1. Intro card */}
      {intro.enabled && (
        <Sequence durationInFrames={introFrames} name="Intro">
          <Intro
            title={intro.title}
            subtitle={intro.subtitle}
            accent={brand.accentColor}
            logo={brand.logo}
          />
        </Sequence>
      )}

      {/* 2. Base video + overlays */}
      <Sequence
        from={introFrames}
        durationInFrames={baseDurationInFrames}
        name="Base"
      >
        <AbsoluteFill>
          <OffthreadVideo src={staticFile(props.baseVideo)} />
        </AbsoluteFill>

        {lowerThirds.map((lt, i) => (
          <Sequence
            key={i}
            from={lt.atFrame}
            durationInFrames={lt.durationInFrames}
            name={`LowerThird ${i + 1}`}
          >
            <LowerThird
              line1={lt.line1}
              line2={lt.line2}
              accent={brand.accentColor}
              durationInFrames={lt.durationInFrames}
            />
          </Sequence>
        ))}

        {captions.enabled && (
          <Captions
            words={captions.words}
            style={captions.style}
            position={captions.position}
            accent={brand.accentColor}
          />
        )}
      </Sequence>

      {/* 3. Outro card */}
      {outro.enabled && (
        <Sequence
          from={introFrames + baseDurationInFrames}
          durationInFrames={outro.durationInFrames}
          name="Outro"
        >
          <Outro
            cta={outro.cta}
            accent={brand.accentColor}
            logo={brand.logo}
          />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
