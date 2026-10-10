import type {
  ParasolidColor,
  ParasolidBodyInput as WriterBody,
} from "./parasolid/types"
import type { ParasolidBodyInput } from "./types"

type Point = [number, number, number]
export interface PlanarRegion {
  loops: number[][]
  normal: Point
  source: number
}

const sub = (a: Point, b: Point): Point => a.map((v, i) => v - b[i]!) as Point
const dot = (a: Point, b: Point) => a.reduce((s, v, i) => s + v * b[i]!, 0)
const cross = (a: Point, b: Point): Point => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
]
const key = (a: number, b: number) => (a < b ? `${a},${b}` : `${b},${a}`)
function areaVector(loop: number[], points: Point[]): Point {
  const origin = points[loop[0]!]!
  const area: Point = [0, 0, 0]
  for (let i = 1; i < loop.length - 1; i++) {
    const c = cross(
      sub(points[loop[i]!]!, origin),
      sub(points[loop[i + 1]!]!, origin),
    )
    for (let axis = 0; axis < 3; axis++) area[axis]! += c[axis]!
  }
  return area
}

/** Validate the original mesh before deleting internal edges, and orient fresh
 * index cycles consistently. Invalid source topology must not disappear in cleanup.
 */
function orientSolid(points: Point[], cycles: number[][]) {
  const uses = new Map<string, { face: number; start: number; end: number }[]>()
  cycles.forEach((cycle, face) =>
    cycle.forEach((start, i) => {
      const end = cycle[(i + 1) % cycle.length]!
      const k = key(start, end)
      const list = uses.get(k) ?? []
      list.push({ face, start, end })
      uses.set(k, list)
    }),
  )
  const adjacency = cycles.map(
    () => [] as { face: number; sameDirection: boolean }[],
  )
  const vertexFaces = points.map(() => new Set<number>())
  const vertexNeighbours = points.map(() => new Map<number, Set<number>>())
  cycles.forEach((cycle, face) =>
    cycle.forEach((vertex) => vertexFaces[vertex]!.add(face)),
  )
  for (const entries of uses.values()) {
    if (entries.length !== 2 || entries[0]!.face === entries[1]!.face) {
      throw new Error(
        `Mesh is open or non-manifold: an edge has ${entries.length} incident faces (expected two)`,
      )
    }
    const [a, b] = entries as [
      (typeof entries)[number],
      (typeof entries)[number],
    ]
    adjacency[a.face]!.push({
      face: b.face,
      sameDirection: a.start === b.start,
    })
    adjacency[b.face]!.push({
      face: a.face,
      sameDirection: a.start === b.start,
    })
    for (const vertex of [a.start, a.end])
      for (const [face, other] of [
        [a.face, b.face],
        [b.face, a.face],
      ]) {
        const neighbours = vertexNeighbours[vertex]!
        const list = neighbours.get(face!) ?? new Set<number>()
        list.add(other!)
        neighbours.set(face!, list)
      }
  }
  vertexFaces.forEach((faces, vertex) => {
    const first = faces.values().next().value!
    const visited = new Set([first])
    const queue = [first]
    for (let i = 0; i < queue.length; i++)
      for (const neighbour of vertexNeighbours[vertex]!.get(queue[i]!) ?? []) {
        if (!visited.has(neighbour)) {
          visited.add(neighbour)
          queue.push(neighbour)
        }
      }
    if (visited.size !== faces.size)
      throw new Error(
        "Mesh is non-manifold: a vertex has disconnected incident face fans",
      )
  })
  const flips = new Map<number, boolean>([[0, false]])
  const queue = [0]
  for (let i = 0; i < queue.length; i++) {
    const face = queue[i]!
    for (const other of adjacency[face]!) {
      const flip = flips.get(face)! !== other.sameDirection
      if (!flips.has(other.face)) {
        flips.set(other.face, flip)
        queue.push(other.face)
      } else if (flips.get(other.face) !== flip)
        throw new Error("Mesh is not orientable")
    }
  }
  if (flips.size !== cycles.length)
    throw new Error("Disconnected shells are not supported in one body")
  cycles.forEach((cycle, face) => {
    if (flips.get(face)) cycle.reverse()
  })
  const origin = points[cycles[0]![0]!]!
  const volume6 = cycles.reduce(
    (sum, cycle) =>
      sum + dot(sub(points[cycle[0]!]!, origin), areaVector(cycle, points)),
    0,
  )
  if (Math.abs(volume6) <= 1e-27) throw new Error("Mesh encloses zero volume")
  if (volume6 < 0) cycles.forEach((cycle) => cycle.reverse())
}

/** Conversion policy: choose larger CAD faces from normalized JSCAD polygons.
 * The serializer receives only the resulting explicitly defined face loops.
 */
export function mergeCoplanarBody(
  body: ParasolidBodyInput,
  units: "mm" | "m" = "mm",
): WriterBody {
  const inputPoints: Point[] = []
  const ids = new Map<string, number>()
  const cycles = body.polygons.map((polygon) =>
    polygon.map((point) => {
      const k = point.join(",")
      let id = ids.get(k)
      if (id === undefined) {
        id = inputPoints.length
        ids.set(k, id)
        inputPoints.push([...point])
      }
      return id
    }),
  )
  const scale = units === "m" ? 1 : 0.001
  const points = inputPoints.map(
    (point) => point.map((value) => value * scale) as Point,
  )
  orientSolid(points, cycles)
  const regions = mergeCoplanarRegions(
    points,
    cycles,
    cycles.map((_, i) => body.faceColors?.[i] ?? body.color),
  )
  return {
    faces: regions.map((region) => ({
      loops: region.loops.map((loop) => loop.map((id) => inputPoints[id]!)),
    })),
    name: body.name,
    color: body.color,
    ...(body.faceColors
      ? {
          faceColors: regions.map((region) => body.faceColors?.[region.source]),
        }
      : {}),
  }
}

/** Reject crossing or almost-touching trimming edges, including between holes.
 * Such regions retain their original polygons instead of producing invalid wires.
 */
function simpleBoundaries(loops: number[][], points: Point[], normal: Point) {
  const drop = normal.map(Math.abs).indexOf(Math.max(...normal.map(Math.abs)))
  const axes = [0, 1, 2].filter((axis) => axis !== drop)
  type P2 = [number, number]
  const project = (id: number): P2 => [
    points[id]![axes[0]!]!,
    points[id]![axes[1]!]!,
  ]
  const distance = (p: P2, a: P2, b: P2) => {
    const dx = b[0] - a[0],
      dy = b[1] - a[1]
    const t = Math.max(
      0,
      Math.min(
        1,
        ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy),
      ),
    )
    return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
  }
  const orient = (a: P2, b: P2, c: P2) =>
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
  const edges = loops.flatMap((loop, ring) =>
    loop.map((id, index) => ({
      a: project(id),
      b: project(loop[(index + 1) % loop.length]!),
      ring,
      index,
      count: loop.length,
    })),
  )
  for (let i = 0; i < edges.length; i++) {
    const e = edges[i]!
    for (let j = i + 1; j < edges.length; j++) {
      const f = edges[j]!
      if (
        e.ring === f.ring &&
        (j === i + 1 || f.index - e.index === e.count - 1)
      )
        continue
      if (
        [0, 1].some(
          (axis) =>
            Math.max(e.a[axis]!, e.b[axis]!) + 1e-9 <
              Math.min(f.a[axis]!, f.b[axis]!) ||
            Math.max(f.a[axis]!, f.b[axis]!) + 1e-9 <
              Math.min(e.a[axis]!, e.b[axis]!),
        )
      )
        continue
      if (
        orient(e.a, e.b, f.a) * orient(e.a, e.b, f.b) < 0 &&
        orient(f.a, f.b, e.a) * orient(f.a, f.b, e.b) < 0
      )
        return false
      if (
        Math.min(
          distance(e.a, f.a, f.b),
          distance(e.b, f.a, f.b),
          distance(f.a, e.a, e.b),
          distance(f.b, e.a, e.b),
        ) <= 1e-9
      )
        return false
    }
  }
  return true
}

/** Input must already be welded, T-junction split, manifold and oriented.
 * Points are in metres. Boundary vertices are retained for neighbouring faces.
 */
export function mergeCoplanarRegions(
  points: Point[],
  cycles: number[][],
  colors: (ParasolidColor | undefined)[],
  enabled = true,
): PlanarRegion[] {
  const normals = cycles.map((cycle) => {
    const area = areaVector(cycle, points)
    const magnitude = Math.hypot(...area)
    return area.map((v) => v / magnitude) as Point
  })
  const uses = new Map<string, number[]>()
  cycles.forEach((cycle, face) =>
    cycle.forEach((a, i) => {
      const k = key(a, cycle[(i + 1) % cycle.length]!)
      const list = uses.get(k) ?? []
      list.push(face)
      uses.set(k, list)
    }),
  )
  const visited = new Set<number>()
  const regions: PlanarRegion[] = []
  for (let seed = 0; seed < cycles.length; seed++) {
    if (visited.has(seed)) continue
    const normal = normals[seed]!
    const origin = points[cycles[seed]![0]!]!
    const color = colors[seed]
    const matches = (face: number) => {
      const otherColor = colors[face]
      if (
        color
          ? !otherColor || color.some((v, i) => v !== otherColor[i])
          : otherColor !== undefined
      )
        return false
      return (
        dot(normal, normals[face]!) > 0 &&
        Math.hypot(...cross(normal, normals[face]!)) <= 1e-10 &&
        cycles[face]!.every(
          (id) => Math.abs(dot(sub(points[id]!, origin), normal)) <= 1e-9,
        )
      )
    }
    const group = [seed]
    visited.add(seed)
    for (let i = 0; enabled && i < group.length; i++) {
      const cycle = cycles[group[i]!]!
      cycle.forEach((a, j) => {
        for (const other of uses.get(key(a, cycle[(j + 1) % cycle.length]!))!) {
          if (visited.has(other) || !matches(other)) continue
          visited.add(other)
          group.push(other)
        }
      })
    }
    const members = new Set(group)
    const boundary = new Map<number, number>()
    let ambiguous = false
    for (const face of group) {
      const cycle = cycles[face]!
      cycle.forEach((a, j) => {
        const b = cycle[(j + 1) % cycle.length]!
        if (uses.get(key(a, b))!.every((other) => members.has(other))) return
        if (boundary.has(a)) ambiguous = true
        boundary.set(a, b)
      })
    }
    const loops: number[][] = []
    while (!ambiguous && boundary.size) {
      const start = boundary.keys().next().value!
      const loop: number[] = []
      let current = start
      do {
        const next = boundary.get(current)
        if (next === undefined) {
          ambiguous = true
          break
        }
        loop.push(current)
        boundary.delete(current)
        current = next
      } while (current !== start)
      if (loop.length < 3) ambiguous = true
      loops.push(loop)
    }
    // A point-touching patch cannot be represented by simple trimming loops.
    // Retain its original faces, rather than changing topology.
    if (ambiguous || loops.length === 0) {
      for (const face of group)
        regions.push({
          loops: [cycles[face]!],
          normal: normals[face]!,
          source: face,
        })
      continue
    }
    const outer = loops.filter(
      (loop) => dot(areaVector(loop, points), normal) > 0,
    )
    if (
      outer.length !== 1 ||
      (group.length > 1 && !simpleBoundaries(loops, points, normal))
    ) {
      for (const face of group)
        regions.push({
          loops: [cycles[face]!],
          normal: normals[face]!,
          source: face,
        })
      continue
    }
    regions.push({
      loops: [outer[0]!, ...loops.filter((loop) => loop !== outer[0])],
      normal,
      source: seed,
    })
  }
  return regions
}
