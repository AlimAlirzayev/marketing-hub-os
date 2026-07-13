# Sensor-backed Ambient Agent

**Status:** prototype-soon

**Score:** 7/10

**Topic:** Sensor-backed ambient agent pattern

**Goal:** Explore local sensor/context patterns without touching real devices by default.

**System integration idea:** Prototype with mock sensors first; later adapt to an office/lab pulse or local hardware demo.

**Acceptance:**
- Initial prototype uses mock images and JSON sensor readings.
- Camera, microphone, serial, Arduino, and actuation are disabled by default.
- Any real hardware, voice, or API spend requires human approval.

**Dependencies:**
- lab/prototypes
- gateway approval rail
- brain local memory

**Risks:**
- camera privacy
- microphone privacy
- device actuation
- API spend

**Next action:** Write a mock-only proof spec if the lab needs a hardware-adjacent demo.

**Evidence:**
- [🔄 Now Plants Can Talk to ChatGPT](https://t.me/perplexity/1028)
- [official source](https://github.com/openai/planttalk)
