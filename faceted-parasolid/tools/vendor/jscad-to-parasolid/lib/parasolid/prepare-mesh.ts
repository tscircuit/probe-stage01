import type { ParasolidPlanarFace, PreparedMesh } from "./types"
import { preparePolygons } from "./normalize-polygons"
import { tolerance, sub, dot, cross, normalOf, edgeKey } from "./mesh-math"

export function prepareMesh(
  faces: readonly ParasolidPlanarFace[],
  scale: number,
): PreparedMesh {
  if (faces.length < 4)
    throw new Error("A closed solid requires at least four faces")
  if (
    faces.some((face) => !Array.isArray(face.loops) || face.loops.length === 0)
  ) {
    throw new Error("Every planar face requires an outer boundary loop")
  }
  const { points, cycles } = preparePolygons(
    faces.flatMap((face) => [...face.loops]),
    scale,
  )
  let offset = 0
  const boundaries = faces.map((face) => {
    const rings = cycles.slice(offset, offset + face.loops.length)
    offset += face.loops.length
    const outer = rings[0]!
    const normal = normalOf(outer, points)
    const origin = points[outer[0]!]!
    for (const hole of rings.slice(1)) {
      if (
        hole.some(
          (id) => Math.abs(dot(sub(points[id]!, origin), normal)) > tolerance,
        )
      ) {
        throw new Error("All loops of a planar face must lie on the same plane")
      }
      // Inner boundaries traverse the face in the opposite direction.
      if (dot(normalOf(hole, points), normal) > 0) hole.reverse()
    }
    return rings
  })

  const uses = new Map<string, { face: number; start: number; end: number }[]>()
  boundaries.forEach((rings, face) => {
    for (const cycle of rings)
      cycle.forEach((start, i) => {
        const end = cycle[(i + 1) % cycle.length]!
        const key = edgeKey(start, end)
        const entries = uses.get(key) ?? []
        entries.push({ face, start, end })
        uses.set(key, entries)
      })
  })
  for (const entries of uses.values()) {
    if (entries.length !== 2 || entries[0]!.face === entries[1]!.face) {
      throw new Error(
        `Mesh is open or non-manifold: an edge has ${entries.length} incident faces (expected two)`,
      )
    }
  }

  // Edge incidence alone misses pinched vertices, where two otherwise closed
  // surface patches touch at a point. The incident faces must form one fan.
  const vertexFaces = points.map(() => new Set<number>())
  const vertexNeighbours = points.map(() => new Map<number, Set<number>>())
  boundaries.forEach((rings, face) => {
    for (const cycle of rings)
      for (const vertex of cycle) vertexFaces[vertex]!.add(face)
  })
  for (const entries of uses.values()) {
    const [a, b] = entries
    for (const vertex of [a!.start, a!.end]) {
      const neighbours = vertexNeighbours[vertex]!
      for (const [face, other] of [
        [a!.face, b!.face],
        [b!.face, a!.face],
      ]) {
        const adjacent = neighbours.get(face!) ?? new Set<number>()
        adjacent.add(other!)
        neighbours.set(face!, adjacent)
      }
    }
  }
  vertexFaces.forEach((faces, vertex) => {
    const first = faces.values().next().value!
    const visited = new Set([first])
    const queue = [first]
    for (let i = 0; i < queue.length; i++) {
      for (const neighbour of vertexNeighbours[vertex]!.get(queue[i]!) ?? []) {
        if (visited.has(neighbour)) continue
        visited.add(neighbour)
        queue.push(neighbour)
      }
    }
    if (visited.size !== faces.size) {
      throw new Error(
        "Mesh is non-manifold: a vertex has disconnected incident face fans",
      )
    }
  })

  // Propagate a consistent orientation. Each shared edge must be traversed in
  // opposite directions by its two faces, regardless of input winding.
  const flips = new Map<number, boolean>([[0, false]])
  const queue = [0]
  for (let q = 0; q < queue.length; q++) {
    const face = queue[q]!
    for (const cycle of boundaries[face]!)
      cycle.forEach((start, i) => {
        const entries = uses.get(
          edgeKey(start, cycle[(i + 1) % cycle.length]!),
        )!
        const own = entries.find((entry) => entry.face === face)!
        const other = entries.find((entry) => entry.face !== face)!
        const flip = flips.get(face)! !== (own.start === other.start)
        if (!flips.has(other.face)) {
          flips.set(other.face, flip)
          queue.push(other.face)
        } else if (flips.get(other.face) !== flip) {
          throw new Error("Mesh is not orientable")
        }
      })
  }
  if (flips.size !== boundaries.length) {
    throw new Error(
      "Disconnected shells are not supported in one body; use one connected shell per body",
    )
  }
  boundaries.forEach((rings, face) => {
    if (flips.get(face)) for (const cycle of rings) cycle.reverse()
  })
  const origin = points[cycles[0]![0]!]!
  let volume6 = 0
  for (const cycle of cycles) {
    const a = sub(points[cycle[0]!]!, origin)
    for (let i = 1; i < cycle.length - 1; i++) {
      volume6 += dot(
        a,
        cross(
          sub(points[cycle[i]!]!, origin),
          sub(points[cycle[i + 1]!]!, origin),
        ),
      )
    }
  }
  if (Math.abs(volume6) <= tolerance ** 3)
    throw new Error("Mesh encloses zero volume")
  if (volume6 < 0) cycles.forEach((cycle) => cycle.reverse())
  return { points, boundaries }
}
