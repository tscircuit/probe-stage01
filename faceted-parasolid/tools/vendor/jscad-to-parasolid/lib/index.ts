import { buildParasolidRepository } from "./build-parasolid"
import { normalizePolygons } from "./parasolid/normalize-polygons"
import { geom3ToPolygons } from "./geom3-to-polygons"
import { resolveGeometries } from "./resolve-geometries"
import { splitConnectedShells } from "./split-connected-shells"
import { normalizeColor } from "./normalize-color"
import { mergeCoplanarBody } from "./merge-coplanar"
import type {
  JscadToParasolidInput,
  JscadToParasolidOptions,
  ParasolidBodyInput,
} from "./types"

export type {
  Geom3Like,
  Geom3Vertex,
  JscadGeometryInput,
  JscadToParasolidInput,
  JscadToParasolidOptions,
  ParasolidBodyInput,
  ParasolidColorInput,
  ParasolidRgbColor,
  Point3,
  RenderedModel,
} from "./types"

/**
 * Resolve JSCAD geometry into world-coordinate polygon bodies, in input units.
 * No caller-owned geometry or matrices are mutated. RGB colors are preserved;
 * alpha is not represented by the supported native color attributes.
 * The converter validates planarity and closed-manifold topology before serialization.
 */
export function jscadToParasolidBodies(
  input: JscadToParasolidInput,
  options: JscadToParasolidOptions = {},
): ParasolidBodyInput[] {
  if (
    options.units !== undefined &&
    options.units !== "mm" &&
    options.units !== "m"
  ) {
    throw new Error('Input units must be "mm" or "m"')
  }
  const bodies: ParasolidBodyInput[] = []
  for (const { geom, name, color } of resolveGeometries(input)) {
    const rawPolygons = geom3ToPolygons(geom)
    if (rawPolygons.length === 0) continue
    const normalized = normalizePolygons(rawPolygons, { units: options.units })
    const bodyColor = normalizeColor(geom.color) ?? color
    const faceColors = new Map(
      normalized.map((polygon, index) => [
        polygon,
        normalizeColor(geom.polygons[index]?.color),
      ]),
    )
    for (const polygons of splitConnectedShells(normalized)) {
      const colors = polygons.map((polygon) => faceColors.get(polygon))
      bodies.push({
        polygons,
        name: name ?? options.name,
        ...(bodyColor ? { color: bodyColor } : {}),
        ...(colors.some((faceColor) => faceColor !== undefined)
          ? { faceColors: colors }
          : {}),
      })
    }
  }
  if (bodies.length === 0) {
    throw new Error(
      "Cannot export an empty model: no solid geometry was provided",
    )
  }
  return bodies
}

/**
 * Convert JSCAD/modelprinter geometry to native Parasolid text (.x_t).
 * Curves remain JSCAD's planar facets; this does not reconstruct analytic curves.
 */
export function jscadToParasolid(
  input: JscadToParasolidInput,
  options: JscadToParasolidOptions = {},
): string {
  const bodies = jscadToParasolidBodies(input, options)
  return buildParasolidRepository(
    options.mergeCoplanarFaces === false
      ? bodies
      : bodies.map((body) => mergeCoplanarBody(body, options.units)),
    { units: options.units },
  ).getString()
}
