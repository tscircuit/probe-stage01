import jscad from "@jscad/modeling"
import {
  executeJscadOperations,
  type JscadImplementation,
  type JscadOperation,
} from "jscad-planner"
import type {
  Geom3Like,
  JscadToParasolidInput,
  ParasolidRgbColor,
} from "./types"
import { geom3ToPolygons } from "./geom3-to-polygons"
import { normalizeColor } from "./normalize-color"

export interface NamedGeometry {
  geom: Geom3Like
  name?: string
  color?: ParasolidRgbColor
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null

function asGeom3(value: unknown, label: string): Geom3Like {
  if (!isRecord(value) || !Array.isArray(value.polygons)) {
    throw new Error(`${label} must be a JSCAD geom3 solid with polygons`)
  }
  return value as unknown as Geom3Like
}

/**
 * The electronics renderer passes geometry arrays to boolean methods, while
 * the planner records those as nested shape arrays. Flatten only those lists,
 * and wrap pre-rendered Custom geometry when it occurs inside a planned tree.
 */
function normalizePlan(value: unknown): JscadOperation {
  if (!isRecord(value)) {
    throw new Error("A planned shape must be a JSCAD operation or geom3")
  }
  if ("polygons" in value) {
    const geom = asGeom3(value, "Planned geometry")
    const operation: JscadOperation = {
      type: "createGeom3",
      polygons: geom3ToPolygons(geom).map((polygon, index) => {
        const color = normalizeColor(geom.polygons[index]?.color)
        return {
          vertices: polygon.map(([x, y, z]) => [x, y, z]),
          ...(color
            ? {
                color: [color[0], color[1], color[2]] as [
                  number,
                  number,
                  number,
                ],
              }
            : {}),
        }
      }),
    }
    const color = normalizeColor(geom.color)
    return color
      ? {
          type: "colorize",
          color: [color[0], color[1], color[2]],
          shape: operation,
        }
      : operation
  }
  if (typeof value.type !== "string") {
    throw new Error("A planned shape must be a JSCAD operation or geom3")
  }
  const operation = { ...value }
  if ("shape" in operation) operation.shape = normalizePlan(operation.shape)
  if ("shapes" in operation) {
    if (!Array.isArray(operation.shapes)) {
      throw new Error("A planned operation's shapes must be an array")
    }
    operation.shapes = operation.shapes.flat(Infinity).map(normalizePlan)
  }
  return operation as unknown as JscadOperation
}

function resolveSolid(value: unknown, label: string): NamedGeometry[] {
  if (isRecord(value) && "polygons" in value) {
    return [{ geom: asGeom3(value, label) }]
  }
  if (!isRecord(value) || typeof value.type !== "string") {
    throw new Error(`${label} must be a JSCAD operation or geom3 solid`)
  }
  // The planner adapter widens JSCAD's tuple parameters to number[], so the
  // adapter cast is needed at this boundary. Returned values are still checked.
  const result: unknown = executeJscadOperations(
    jscad as unknown as JscadImplementation<Geom3Like>,
    normalizePlan(value),
  )
  return (Array.isArray(result) ? result : [result]).map((geom, index) => ({
    geom: asGeom3(geom, `${label} operation result ${index}`),
  }))
}

export function resolveGeometries(
  input: JscadToParasolidInput,
): NamedGeometry[] {
  if (Array.isArray(input)) {
    return input.flatMap((geom, index) =>
      resolveSolid(geom, `Geometry ${index}`),
    )
  }

  if (!isRecord(input)) {
    throw new Error("Expected a JSCAD operation, geom3, or rendered model")
  }

  if ("geometries" in input) {
    if (!Array.isArray(input.geometries)) {
      throw new Error("Rendered model geometries must be an array")
    }
    return input.geometries.flatMap((entry: unknown, index: number) => {
      if (!isRecord(entry)) {
        throw new Error(
          `Rendered geometry ${index} must contain a geom3 or operation`,
        )
      }
      return resolveSolid(entry.geom, `Rendered geometry ${index}`).map(
        ({ geom }) => ({
          geom,
          color: normalizeColor(
            geom.color ?? (entry.color as Geom3Like["color"]),
          ),
          ...(typeof entry.name === "string" ? { name: entry.name } : {}),
        }),
      )
    })
  }

  return resolveSolid(input, "Geometry")
}
