import type { Geom3Like, Geom3Vertex, Point3 } from "./types"

function readPoint(vertex: Geom3Vertex, label: string): Point3 {
  const coordinates =
    vertex && typeof vertex === "object" && "pos" in vertex
      ? vertex.pos
      : vertex && typeof vertex === "object" && "position" in vertex
        ? vertex.position
        : vertex
  if (
    !coordinates ||
    typeof coordinates !== "object" ||
    !("length" in coordinates) ||
    coordinates.length < 3
  ) {
    throw new Error(`${label} must contain three finite coordinates`)
  }
  const x = coordinates[0]
  const y = coordinates[1]
  const z = coordinates[2]
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof z !== "number" ||
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    !Number.isFinite(z)
  ) {
    throw new Error(`${label} must contain three finite coordinates`)
  }
  return [x, y, z]
}

/** Extracts fresh coordinates without applying JSCAD's mutating toPolygons. */
export function geom3ToPolygons(geom: Geom3Like): Point3[][] {
  const transform = geom.transforms
  let mirrored = false
  let matrix: number[] | undefined
  if (transform !== undefined) {
    if (transform.length !== 16) {
      throw new Error("Geometry transforms must contain 16 finite numbers")
    }
    matrix = Array.from(transform)
    if (!matrix.every((n) => typeof n === "number" && Number.isFinite(n))) {
      throw new Error("Geometry transforms must contain 16 finite numbers")
    }
    if (
      matrix[3] !== 0 ||
      matrix[7] !== 0 ||
      matrix[11] !== 0 ||
      matrix[15] !== 1
    ) {
      throw new Error("Geometry transforms must be affine (no perspective)")
    }
    const determinant =
      matrix[0]! * (matrix[5]! * matrix[10]! - matrix[6]! * matrix[9]!) -
      matrix[4]! * (matrix[1]! * matrix[10]! - matrix[2]! * matrix[9]!) +
      matrix[8]! * (matrix[1]! * matrix[6]! - matrix[2]! * matrix[5]!)
    if (!Number.isFinite(determinant) || determinant === 0) {
      throw new Error("Geometry transforms must be invertible")
    }
    mirrored = determinant < 0
  }

  return geom.polygons.map((polygon, polygonIndex) => {
    if (
      !polygon ||
      !Array.isArray(polygon.vertices) ||
      polygon.vertices.length < 3
    ) {
      throw new Error(
        `Polygon ${polygonIndex} must have at least three vertices`,
      )
    }
    const points = polygon.vertices.map((vertex, vertexIndex) => {
      const [x, y, z] = readPoint(
        vertex,
        `Polygon ${polygonIndex} vertex ${vertexIndex}`,
      )
      if (!matrix) return [x, y, z] as Point3
      const point: Point3 = [
        matrix[0]! * x + matrix[4]! * y + matrix[8]! * z + matrix[12]!,
        matrix[1]! * x + matrix[5]! * y + matrix[9]! * z + matrix[13]!,
        matrix[2]! * x + matrix[6]! * y + matrix[10]! * z + matrix[14]!,
      ]
      if (!point.every(Number.isFinite)) {
        throw new Error(
          `Polygon ${polygonIndex} has non-finite transformed coordinates`,
        )
      }
      return point
    })
    // A reflection changes handedness. JSCAD reverses the face loops too.
    if (mirrored) points.reverse()
    return points
  })
}
