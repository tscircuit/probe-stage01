import type {
  Point,
  ParasolidPoint,
  ParasolidPolygons,
  ParasolidWriteOptions,
} from "./types"
import { tolerance, sub, dot, cross, length, normalOf } from "./mesh-math"

export function preparePolygons(polygons: ParasolidPolygons, scale: number) {
  if (polygons.length < 4)
    throw new Error("A closed solid requires at least four polygons")
  const points: Point[] = []
  const inputPoints: Point[] = []
  const bins = new Map<string, number[]>()
  const vertex = (input: ParasolidPoint): number => {
    if (input.length !== 3 || !input.every(Number.isFinite)) {
      throw new Error("Every vertex must contain three finite coordinates")
    }
    const p = input.map((value) => value * scale) as Point
    if (!p.every(Number.isFinite))
      throw new Error("Vertex coordinate is out of range")
    const cell = p.map((value) => Math.floor(value / tolerance)) as Point
    for (let x = -1; x <= 1; x++) {
      for (let y = -1; y <= 1; y++) {
        for (let z = -1; z <= 1; z++) {
          const nearby = bins.get(
            `${cell[0] + x},${cell[1] + y},${cell[2] + z}`,
          )
          for (const index of nearby ?? []) {
            if (length(sub(points[index]!, p)) <= tolerance) return index
          }
        }
      }
    }
    const index = points.length
    points.push(p)
    inputPoints.push([...input])
    const key = cell.join(",")
    const bucket = bins.get(key) ?? []
    bucket.push(index)
    bins.set(key, bucket)
    return index
  }
  let cycles = polygons.map((polygon) => {
    const ids = polygon.map(vertex)
    if (ids.length > 1 && ids[0] === ids[ids.length - 1]) ids.pop()
    if (ids.length < 3 || new Set(ids).size !== ids.length) {
      throw new Error(
        "Polygon must have at least three distinct vertices without repeated edges",
      )
    }
    const normal = normalOf(ids, points)
    const origin = points[ids[0]!]!
    if (
      ids.some(
        (id) => Math.abs(dot(sub(points[id]!, origin), normal)) > tolerance,
      )
    ) {
      throw new Error("Only planar polygons can be written to Parasolid")
    }
    return ids
  })

  // JSCAD boolean operations can leave a vertex on the middle of a neighbour's
  // edge. Both faces must use the same set of topological edges in a B-rep.
  cycles = cycles.map((cycle) =>
    cycle.flatMap((start, i) => {
      const end = cycle[(i + 1) % cycle.length]!
      const a = points[start]!
      const delta = sub(points[end]!, a)
      const squared = dot(delta, delta)
      const edgeLength = Math.sqrt(squared)
      const splits: { index: number; fraction: number }[] = [
        { index: start, fraction: 0 },
      ]
      points.forEach((p, index) => {
        if (index === start || index === end) return
        const relative = sub(p, a)
        const fraction = dot(relative, delta) / squared
        if (
          fraction <= tolerance / edgeLength ||
          fraction >= 1 - tolerance / edgeLength
        )
          return
        const distance = length(cross(relative, delta)) / edgeLength
        if (distance <= tolerance) splits.push({ index, fraction })
      })
      return splits
        .sort((a, b) => a.fraction - b.fraction)
        .map((split) => split.index)
    }),
  )

  return { points, inputPoints, cycles }
}

export function inputScale(options: Pick<ParasolidWriteOptions, "units">) {
  if (
    options.units !== undefined &&
    options.units !== "mm" &&
    options.units !== "m"
  ) {
    throw new Error("Input units must be 'mm' or 'm'")
  }
  return options.units === "m" ? 1 : 0.001
}

/**
 * Weld matching vertices and split CSG T-junctions before dividing a mesh into
 * edge-connected shells. Returns fresh coordinates in the original input unit.
 * The welding tolerance is 1e-9 metres (1e-6 millimetres). This checks polygon
 * planarity and degeneracy; full closed-manifold validation happens on write.
 */
export function normalizePolygons(
  polygons: ParasolidPolygons,
  options: Pick<ParasolidWriteOptions, "units"> = {},
): ParasolidPoint[][] {
  const scale = inputScale(options)
  const { inputPoints, cycles } = preparePolygons(polygons, scale)
  return cycles.map((cycle) =>
    cycle.map((index) => [...inputPoints[index]!] as Point),
  )
}
