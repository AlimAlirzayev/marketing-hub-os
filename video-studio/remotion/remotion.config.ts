// Remotion CLI configuration. render.py drives renders through the CLI, so
// only project-wide defaults belong here.
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setChromiumOpenGlRenderer("angle");
