// Composition registry. The "Final" composition is the only one render.py
// renders; its size and length come entirely from public/props.json via
// calculateMetadata, so one composition serves every aspect ratio.
import React from "react";
import { Composition } from "remotion";
import { Final } from "./Final";
import { DEFAULT_PROPS, FinalProps } from "./types";

const totalDuration = (props: FinalProps): number => {
  const intro = props.intro.enabled ? props.intro.durationInFrames : 0;
  const outro = props.outro.enabled ? props.outro.durationInFrames : 0;
  return intro + props.baseDurationInFrames + outro;
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Final"
      component={Final}
      defaultProps={DEFAULT_PROPS}
      // Dimensions and length are unknown until props.json is supplied;
      // calculateMetadata resolves them per render.
      calculateMetadata={({ props }) => ({
        durationInFrames: totalDuration(props),
        width: props.width,
        height: props.height,
        fps: props.fps,
      })}
      // Placeholders; overridden by calculateMetadata above.
      durationInFrames={300}
      width={1080}
      height={1080}
      fps={30}
    />
  );
};
