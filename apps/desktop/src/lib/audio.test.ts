import { describe, expect, it } from "vitest";

import { normalizeMicTranscript, sanitizeSpeechText } from "./audio";

describe("audio helpers", () => {
  it("corrects common rate-query homophones without rewriting the prompt", () => {
    expect(normalizeMicTranscript("gold right")).toBe("gold rate");
    expect(normalizeMicTranscript("what is the mortgage right today")).toBe("what is the mortgage rate today");
  });

  it("removes markdown markers before TTS", () => {
    expect(sanitizeSpeechText("**Step 1:** *Open* Kaggle")).toBe("Step 1: Open Kaggle");
  });
});
