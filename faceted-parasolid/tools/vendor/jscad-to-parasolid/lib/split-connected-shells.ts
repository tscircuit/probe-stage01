import type { Point3 } from "./types"

function signedVolume(polygons: readonly (readonly Point3[])[]): number {
  // Moving the origin to a vertex avoids cancellation for translated models.
  const origin = polygons[0]?.[0]
  if (!origin) return 0
  let volume = 0
  for (const polygon of polygons) {
    const first = polygon[0]!
    const a = first.map((n, i) => n - origin[i]!)
    for (let i = 1; i < polygon.length - 1; i++) {
      const b = polygon[i]!.map((n, axis) => n - origin[axis]!)
      const c = polygon[i + 1]!.map((n, axis) => n - origin[axis]!)
      volume +=
        (a[0]! * (b[1]! * c[2]! - b[2]! * c[1]!) +
          a[1]! * (b[2]! * c[0]! - b[0]! * c[2]!) +
          a[2]! * (b[0]! * c[1]! - b[1]! * c[0]!)) /
        6
    }
  }
  return volume
}

/** Split already welded, T-junction-free polygons by shared edges. */
export function splitConnectedShells(polygons: Point3[][]): Point3[][][] {
  const parent = polygons.map((_, index) => index)
  const find = (index: number): number => {
    let root = index
    while (parent[root] !== root) root = parent[root]!
    while (index !== root) {
      const next = parent[index]!
      parent[index] = root
      index = next
    }
    return root
  }

  const owners = new Map<string, number>()
  polygons.forEach((polygon, index) => {
    for (let vertex = 0; vertex < polygon.length; vertex++) {
      const a = polygon[vertex]!.join(",")
      const b = polygon[(vertex + 1) % polygon.length]!.join(",")
      const key = a < b ? `${a}|${b}` : `${b}|${a}`
      const other = owners.get(key)
      if (other === undefined) owners.set(key, index)
      else parent[find(index)] = find(other)
    }
  })

  const groups = new Map<number, Point3[][]>()
  polygons.forEach((polygon, index) => {
    const root = find(index)
    const group = groups.get(root)
    if (group) group.push(polygon)
    else groups.set(root, [polygon])
  })
  const shells = [...groups.values()]
  // Some renderer-recorded extrusions have the entire boundary reversed. A
  // single connected shell can safely be oriented outward, as topology construction also
  // does. An inward component alongside other shells may describe a cavity and
  // must not silently become an additional filled solid.
  if (shells.length === 1 && signedVolume(shells[0]!) < 0) {
    // These are fresh normalized arrays. Retain their identity so callers can
    // map polygon metadata (such as face color) through shell separation.
    for (const polygon of shells[0]!) polygon.reverse()
    return shells
  }
  for (const shell of shells) {
    if (signedVolume(shell) < 0) {
      throw new Error(
        "Inward-facing component: enclosed cavity shells are not supported",
      )
    }
  }
  return shells
}
