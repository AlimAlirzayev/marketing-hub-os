// Word-timed captions. "karaoke" highlights each word as it is spoken;
// "block" simply shows the current phrase. Words are chunked into short
// phrases so the viewer never reads more than a line at a time.
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_STACK } from "../theme";
import { CaptionWord } from "../types";

type Props = {
  words: CaptionWord[];
  style: "karaoke" | "block";
  position: "bottom" | "center" | "top";
  accent: string;
};

const PHRASE_LEN = 5; // words per on-screen phrase

const chunk = (words: CaptionWord[]): CaptionWord[][] => {
  const out: CaptionWord[][] = [];
  for (let i = 0; i < words.length; i += PHRASE_LEN) {
    out.push(words.slice(i, i + PHRASE_LEN));
  }
  return out;
};

const justifyFor = (pos: Props["position"]): React.CSSProperties["justifyContent"] =>
  pos === "top" ? "flex-start" : pos === "center" ? "center" : "flex-end";

export const Captions: React.FC<Props> = ({
  words,
  style,
  position,
  accent,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = frame / fps;

  if (words.length === 0) return null;

  // Index of the most recently started word.
  let activeIdx = -1;
  for (let i = 0; i < words.length; i++) {
    if (words[i].start <= time) activeIdx = i;
    else break;
  }
  if (activeIdx < 0) return null;

  const phrases = chunk(words);
  const phrase = phrases[Math.floor(activeIdx / PHRASE_LEN)];
  const localActive = activeIdx % PHRASE_LEN;

  return (
    <AbsoluteFill
      style={{
        fontFamily: FONT_STACK,
        justifyContent: justifyFor(position),
        alignItems: "center",
        padding: position === "center" ? "0 10%" : "120px 8%",
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "0 16px",
          maxWidth: "86%",
        }}
      >
        {phrase.map((word, i) => {
          const spoken = style === "karaoke" && i <= localActive;
          return (
            <span
              key={i}
              style={{
                fontSize: 56,
                fontWeight: 800,
                lineHeight: 1.25,
                color: spoken ? accent : COLORS.white,
                textShadow: "0 4px 18px rgba(0,0,0,0.85)",
                transform:
                  style === "karaoke" && i === localActive
                    ? "scale(1.08)"
                    : "scale(1)",
                transition: "transform 80ms ease-out",
              }}
            >
              {word.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
