// Remotion entry point. render.py invokes:
//   npx remotion render src/index.ts Final <out> --props=public/props.json
import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
