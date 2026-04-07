import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

import React from "react";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";

const [, , inputPath, outputDir] = process.argv;

if (!inputPath || !outputDir) {
  throw new Error("Usage: node render-instagram.mjs <input.json> <output_dir>");
}

const payload = JSON.parse(fs.readFileSync(inputPath, "utf8"));
fs.mkdirSync(outputDir, { recursive: true });

const width = 1080;
const height = 1350;
const bottomSafeInset = 170;
const palette = {
  ai_news: { accent: "#ff8a00", muted: "#7d7d7d", panel: "#101010" },
  ai_explained: { accent: "#ffe600", muted: "#7d7d7d", panel: "#0e0e0e" },
  ai_for_business: { accent: "#4dffb8", muted: "#7d7d7d", panel: "#0f1412" }
};

const fonts = loadFonts();

function SlideView({ lane, title, slide, totalSlides }) {
  const theme = palette[lane] ?? palette.ai_explained;
  const accent = theme.accent;
  const slideType = resolveSlideType(slide, totalSlides);
  if (slideType === "hook") {
    return React.createElement(HookSlide, { lane, title, slide, totalSlides, accent, theme });
  }
  if (slideType === "closing") {
    return React.createElement(ClosingSlide, { lane, title, slide, totalSlides, accent, theme });
  }
  return React.createElement(InteriorSlide, { lane, title, slide, totalSlides, accent, theme, slideType });
}

function BaseFrame({ accent, children }) {
  return React.createElement(
    "div",
    {
      style: {
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: "#050505",
        color: "#f7f7f2",
        fontFamily: "NewsbotSans",
        padding: "52px 64px 0 64px",
        position: "relative",
        overflow: "hidden"
      }
    },
    React.createElement("div", {
      style: {
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: 8,
        background: accent
      }
    }),
    children
  );
}

function HookSlide({ lane, title, slide, accent, theme }) {
  const chunks = splitHeadlineForLane(slide.headline, lane, "hook");
  return React.createElement(
    BaseFrame,
    { accent },
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center"
        }
      },
      React.createElement(
        "div",
        {
          style: {
            fontSize: 22,
            letterSpacing: 2.8,
            color: theme.muted,
            textTransform: "uppercase"
          }
        },
        lane.replaceAll("_", " ")
      )
    ),
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          flexDirection: "column",
          gap: 20,
          marginTop: 120,
          maxWidth: 920
        }
      },
      React.createElement(
        "div",
        {
          style: {
            fontSize: 24,
            color: "#686868",
            maxWidth: 760,
            letterSpacing: -0.4
          }
        },
        title
      ),
      ...chunks.map((chunk, index) =>
        React.createElement(
          "div",
          {
            key: `hook-${index}`,
            style: {
              fontSize: lane === "ai_news" ? 116 : 124,
              lineHeight: lane === "ai_news" ? 0.9 : 0.92,
              letterSpacing: -4.6,
              textTransform: "uppercase",
              fontWeight: chunk.highlight ? 800 : 700,
              color: chunk.highlight ? accent : "#f7f7f2",
              maxWidth: 940
            }
          },
          chunk.text
        )
      )
    ),
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          paddingBottom: `${bottomSafeInset}px`
        }
      },
      React.createElement(
        "div",
        {
          style: {
            fontSize: 20,
            letterSpacing: 2.4,
            color: theme.muted,
            textTransform: "uppercase"
          }
        },
        "Hook"
      ),
      React.createElement(
        "div",
        {
          style: {
            width: 168,
            height: 10,
            borderRadius: 999,
            background: accent
          }
        }
      )
    )
  );
}

function InteriorSlide({ lane, title, slide, totalSlides, accent, theme, slideType }) {
  const variant = resolveInteriorVariant(lane, slide, slideType);
  const chunks = splitHeadlineForLane(slide.headline, lane, variant);
  const bodyWidth = variant === "interior_proof" ? 620 : variant === "interior_operator" ? 560 : 760;
  const headlineSize = variant === "interior_proof" ? 62 : variant === "interior_operator" ? 82 : 88;
  const roleLabel = slide.role.replaceAll("_", " ");
  return React.createElement(
    BaseFrame,
    { accent },
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center"
        }
      },
      React.createElement(
        "div",
        {
          style: {
            fontSize: 22,
            letterSpacing: 2.8,
            color: theme.muted,
            textTransform: "uppercase"
          }
        },
        lane.replaceAll("_", " ")
      ),
      React.createElement(
        "div",
        {
          style: {
            fontSize: 22,
            color: "#7b7b7b"
          }
        },
        `Slide ${slide.slide_number}`
      )
    ),
    React.createElement(
      "div",
        {
          style: {
            display: "flex",
            flexDirection: variant === "interior_operator" ? "row" : "column",
            gap: variant === "interior_operator" ? 30 : 18,
            marginTop: 124,
            maxWidth: 920
          }
        },
      variant === "interior_operator"
        ? React.createElement(
            "div",
            {
              style: {
                display: "flex",
                flexDirection: "column",
                gap: 18,
                width: 180,
                paddingTop: 6
              }
            },
            React.createElement(
              "div",
              {
                style: {
                  fontSize: 18,
                  color: accent,
                  textTransform: "uppercase",
                  letterSpacing: 2.2,
                  marginBottom: 18
                }
              },
              roleLabel
            ),
            React.createElement("div", {
              style: {
                width: 12,
                height: 240,
                borderRadius: 999,
                background: accent
              }
            })
          )
        : null,
      React.createElement(
        "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            gap: variant === "interior_proof" ? 20 : 18,
            flex: 1
          }
        },
        React.createElement(
          "div",
          {
            style: {
              fontSize: 23,
              color: "#707070",
              maxWidth: 740
            }
          },
          title
        ),
        variant === "interior_proof"
          ? React.createElement(
              "div",
              {
                style: {
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                  padding: "28px 30px 30px 30px",
                  borderRadius: 28,
                  border: `1px solid ${accent}55`,
                  background: theme.panel
                }
              },
              React.createElement(
                "div",
                {
                  style: {
                    fontSize: 18,
                    color: accent,
                    textTransform: "uppercase",
                    letterSpacing: 2.2
                  }
                },
                roleLabel
              ),
              ...chunks.map((chunk, index) =>
                React.createElement(
                  "div",
                  {
                    key: `interior-${index}`,
                    style: {
                      fontSize: headlineSize,
                      lineHeight: 0.94,
                      letterSpacing: -3,
                      textTransform: "uppercase",
                      fontWeight: chunk.highlight ? 800 : 700,
                      color: chunk.highlight ? accent : "#f7f7f2",
                      maxWidth: 820
                    }
                  },
                  chunk.text
                )
              ),
              React.createElement(
                "div",
                {
                  style: {
                    fontSize: 28,
                    lineHeight: 1.24,
                    color: "#c1c1c1",
                    maxWidth: 820,
                    marginTop: 2
                  }
                },
                slide.support
              )
            )
          : React.createElement(
              React.Fragment,
              null,
              variant !== "interior_operator"
                ? React.createElement(
                    "div",
                    {
                      style: {
                        fontSize: 18,
                        color: accent,
                        textTransform: "uppercase",
                        letterSpacing: 2.2,
                        marginBottom: 6
                      }
                    },
                    roleLabel
                  )
                : null,
              ...chunks.map((chunk, index) =>
                React.createElement(
                  "div",
                  {
                    key: `interior-${index}`,
                    style: {
                      fontSize: headlineSize,
                      lineHeight: 0.95,
                      letterSpacing: -3.2,
                      textTransform: "uppercase",
                      fontWeight: chunk.highlight ? 800 : 700,
                      color: chunk.highlight ? accent : "#f7f7f2",
                      maxWidth: 920
                    }
                  },
                  chunk.text
                )
              ),
              React.createElement(
                "div",
                {
                  style: {
                    fontSize: variant === "interior_operator" ? 28 : 30,
                    lineHeight: 1.24,
                    color: variant === "interior_operator" ? "#d0d0d0" : "#9b9b9b",
                    maxWidth: bodyWidth,
                    marginTop: 8
                  }
                },
                slide.support
              )
            )
      )
    ),
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          paddingBottom: `${bottomSafeInset}px`
        }
      },
      React.createElement(
        "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            gap: 18
          }
        },
        React.createElement(
          "div",
          {
            style: {
              fontSize: 20,
              color: theme.muted,
              textTransform: "uppercase",
              letterSpacing: 2.4
            }
          },
          roleLabel
        ),
        React.createElement(
          "div",
          {
            style: {
              display: "flex",
              gap: 10,
              alignItems: "center"
            }
          },
          ...Array.from({ length: totalSlides }, (_, index) =>
            React.createElement("div", {
              key: `dot-${index + 1}`,
              style: {
                width: index + 1 === slide.slide_number ? 40 : 12,
                height: 12,
                borderRadius: 999,
                background: index + 1 === slide.slide_number ? accent : "#2c2c2c",
                border: index + 1 === slide.slide_number ? `1px solid ${accent}` : "1px solid #3a3a3a"
              }
            })
          )
        )
      ),
      React.createElement(
        "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 12
          }
        },
        React.createElement(
          "div",
          {
            style: {
              fontSize: 36,
              color: accent,
              fontWeight: 800
            }
          },
          "\u2192"
        ),
        React.createElement(
          "div",
          {
            style: {
              fontSize: 18,
              letterSpacing: 2.2,
              color: theme.muted,
              textTransform: "uppercase"
            }
          },
          "Newsbot"
        )
      )
    )
  );
}

function ClosingSlide({ lane, title, slide, accent, theme }) {
  const ctaChunks = buildClosingHeadline(slide, lane);
  return React.createElement(
    BaseFrame,
    { accent },
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center"
        }
      },
      React.createElement(
        "div",
        {
          style: {
            fontSize: 22,
            letterSpacing: 2.8,
            color: theme.muted,
            textTransform: "uppercase"
          }
        },
        lane.replaceAll("_", " ")
      )
    ),
    React.createElement(
      "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            gap: 24,
            marginTop: 136,
            maxWidth: 910
          }
        },
      React.createElement(
        "div",
        {
          style: {
            fontSize: 26,
            color: accent,
            textTransform: "uppercase",
            letterSpacing: 3.4
          }
        },
        "@newsbot"
      ),
      ...ctaChunks.map((chunk, index) =>
        React.createElement(
          "div",
          {
            key: `closing-${index}`,
            style: {
              fontSize: index === 0 ? 122 : 108,
              lineHeight: 0.9,
              letterSpacing: -4.2,
              textTransform: "uppercase",
              fontWeight: 800,
              color: chunk.highlight ? accent : "#f7f7f2"
            }
          },
          chunk.text
        )
      ),
      React.createElement(
        "div",
        {
          style: {
            fontSize: 32,
            lineHeight: 1.24,
            color: "#b2b2b2",
            maxWidth: 760,
            marginTop: 4
          }
        },
        slide.support
      )
    ),
    React.createElement(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          paddingBottom: `${bottomSafeInset}px`
        }
      },
      React.createElement(
        "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            gap: 18
          }
        },
        React.createElement(
          "div",
          {
            style: {
              fontSize: 20,
              color: theme.muted,
              textTransform: "uppercase",
              letterSpacing: 2.4
            }
          },
          "Closing CTA"
        )
      ),
      React.createElement(
        "div",
        {
          style: {
              width: 196,
              height: 16,
              borderRadius: 999,
              background: accent
            }
        }
      )
    )
  );
}

const slides = [];
for (const slide of payload.slides ?? []) {
  const svg = await satori(
    React.createElement(SlideView, {
      lane: payload.lane,
      title: payload.title,
      slide,
      totalSlides: payload.slides?.length ?? 1
    }),
    {
      width,
      height,
      fonts
    }
  );
  const resvg = new Resvg(svg, { fitTo: { mode: "width", value: width } });
  const png = resvg.render().asPng();
  const filename = `slide-${String(slide.slide_number).padStart(2, "0")}.png`;
  fs.writeFileSync(path.join(outputDir, filename), png);
  slides.push({
    slide_number: slide.slide_number,
    filename,
    width,
    height,
    template_id: slide.template_id ?? null,
    template_version: slide.template_version ?? null,
    schema_version: slide.schema_version ?? payload.schema_version ?? null,
    content_hash: crypto.createHash("sha256").update(png).digest("hex")
  });
}

process.stdout.write(JSON.stringify({ slides }));

function resolveSlideType(slide, totalSlides) {
  if ((slide.layout_family || "") === "hook" || slide.slide_number === 1) {
    return "hook";
  }
  if ((slide.layout_family || "") === "closing" || slide.slide_number === totalSlides) {
    return "closing";
  }
  return slide.layout_family || "interior_statement";
}

function splitHeadlineForLane(headline, lane, variant) {
  if (lane === "ai_news" && variant === "hook") {
    return splitNewsHook(headline);
  }
  if (variant === "closing") {
    return splitHeadline(headline, 2);
  }
  return splitHeadline(headline, variant === "interior_proof" ? 3 : 2);
}

function splitHeadline(headline, chunkSize) {
  const words = String(headline || "")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean);
  if (words.length <= chunkSize) {
    return [words.join(" ")];
  }
  const highlightCount = Math.max(2, Math.ceil(words.length / 3));
  const normalWords = words.slice(0, words.length - highlightCount);
  const highlightWords = words.slice(words.length - highlightCount);
  const lines = [];
  if (normalWords.length) {
    lines.push(...chunkWords(normalWords, chunkSize).map((text) => ({ text, highlight: false })));
  }
  lines.push(...chunkWords(highlightWords, chunkSize).map((text) => ({ text, highlight: true })));
  return lines;
}

function splitNewsHook(headline) {
  const words = String(headline || "")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean);
  if (!words.length) {
    return [];
  }
  const emphasisTerms = ["extra", "pay", "pricing", "billing", "cost", "subscription", "launch", "access", "ban", "limit"];
  let pivot = words.findIndex((word) => emphasisTerms.includes(word.toLowerCase()));
  if (pivot < 0) {
    pivot = Math.max(2, words.length - 3);
  }
  const lead = words.slice(0, pivot);
  const payoff = words.slice(pivot);
  const lines = [];
  if (lead.length) {
    lines.push(...chunkWords(lead, 2).map((text) => ({ text, highlight: false })));
  }
  if (payoff.length) {
    lines.push(...chunkWords(payoff, 2).map((text) => ({ text, highlight: true })));
  }
  return lines;
}

function resolveInteriorVariant(lane, slide, slideType) {
  if (slideType === "interior_proof") {
    return "interior_proof";
  }
  if (lane === "ai_for_business" && ["pain_point", "mistake", "better_way", "workflow", "outcome"].includes(slide.role)) {
    return "interior_operator";
  }
  if (lane === "ai_news" && ["what_changed", "why_now", "who_it_affects", "implication"].includes(slide.role)) {
    return "interior_news";
  }
  return "interior_statement";
}

function buildClosingHeadline(slide, lane) {
  const support = String(slide.support || "").toLowerCase();
  const action = support.includes("share")
    ? "SHARE THIS"
    : support.includes("follow")
      ? "SAVE AND FOLLOW"
      : support.includes("save")
        ? "SAVE THIS"
        : "KEEP THIS";
  const laneWord = lane === "ai_news" ? "UPDATES" : lane === "ai_for_business" ? "IDEAS" : "BREAKDOWNS";
  return [
    { text: action, highlight: false },
    { text: laneWord, highlight: true }
  ];
}

function chunkWords(words, size) {
  const chunks = [];
  for (let index = 0; index < words.length; index += size) {
    chunks.push(words.slice(index, index + size).join(" "));
  }
  return chunks;
}

function loadFonts() {
  const regularPath = firstExisting([
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
  ]);
  const boldPath = firstExisting([
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
  ]);
  if (!regularPath || !boldPath) {
    throw new Error("No usable system fonts found for Instagram renderer");
  }
  return [
    {
      name: "NewsbotSans",
      data: fs.readFileSync(regularPath),
      weight: 400,
      style: "normal"
    },
    {
      name: "NewsbotSans",
      data: fs.readFileSync(boldPath),
      weight: 800,
      style: "normal"
    }
  ];
}

function firstExisting(candidates) {
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}
