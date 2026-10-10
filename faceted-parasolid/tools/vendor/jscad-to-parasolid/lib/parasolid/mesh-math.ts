import type { Point } from "./types"

// Below Parasolid's usual 1e-8 m linear resolution. Used only to weld matching
// vertices and split polygon edges at existing vertices (CSG T-junctions).
export const tolerance = 1e-9
export const sub = (a: Point, b: Point): Point => [
  a[0] - b[0],
  a[1] - b[1],
  a[2] - b[2],
]
export const dot = (a: Point, b: Point) =>
  a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
export const cross = (a: Point, b: Point): Point => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
]
export const length = (a: Point) => Math.hypot(...a)
export const unit = (a: Point): Point => {
  const magnitude = length(a)
  return [a[0] / magnitude, a[1] / magnitude, a[2] / magnitude]
}
export const edgeKey = (a: number, b: number) =>
  a < b ? `${a},${b}` : `${b},${a}`

export function normalOf(cycle: number[], points: Point[]): Point {
  const origin = points[cycle[0]!]!
  const sum: Point = [0, 0, 0]
  for (let i = 1; i < cycle.length - 1; i++) {
    const area = cross(
      sub(points[cycle[i]!]!, origin),
      sub(points[cycle[i + 1]!]!, origin),
    )
    for (let axis = 0; axis < 3; axis++) sum[axis]! += area[axis]!
  }
  if (length(sum) <= tolerance * tolerance)
    throw new Error("Polygon has zero area")
  return unit(sum)
}
