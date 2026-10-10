import jscad from "@jscad/modeling"
import type { ParasolidColorInput, ParasolidRgbColor } from "./types"

/** RGB/RGBA, byte RGB, hexadecimal CSS notation, and named CSS colors. */
export function normalizeColor(
  color: ParasolidColorInput | undefined,
): ParasolidRgbColor | undefined {
  if (color === undefined) return undefined
  if (Array.isArray(color)) {
    if (
      (color.length !== 3 && color.length !== 4) ||
      !color.every(
        (channel) => typeof channel === "number" && Number.isFinite(channel),
      )
    ) {
      throw new Error(
        "Color must contain three or four finite numeric channels",
      )
    }
    const rgb = color.slice(0, 3)
    const scale = rgb.some((channel) => channel > 1) ? 255 : 1
    if (color.some((channel) => channel < 0 || channel > scale)) {
      throw new Error("Color channels must be in the range 0–1 or 0–255")
    }
    // X_T color attributes in the supported subset carry RGB, not alpha.
    return [rgb[0]! / scale, rgb[1]! / scale, rgb[2]! / scale]
  }
  if (typeof color === "string") {
    const text = color.trim()
    const hex = text.replace(/^#/, "")
    if (/^(?:[\da-f]{3}|[\da-f]{4}|[\da-f]{6}|[\da-f]{8})$/i.test(hex)) {
      const expanded =
        hex.length <= 4
          ? hex
              .split("")
              .map((channel) => channel + channel)
              .join("")
          : hex
      return [
        Number.parseInt(expanded.slice(0, 2), 16) / 255,
        Number.parseInt(expanded.slice(2, 4), 16) / 255,
        Number.parseInt(expanded.slice(4, 6), 16) / 255,
      ]
    }
    const named: unknown = jscad.colors.colorNameToRgb(text)
    if (
      Array.isArray(named) &&
      named.length === 3 &&
      named.every(Number.isFinite)
    ) {
      return [named[0]!, named[1]!, named[2]!]
    }
  }
  throw new Error(
    "Unsupported color: use RGB/RGBA channels, hexadecimal notation, or a CSS color name",
  )
}
