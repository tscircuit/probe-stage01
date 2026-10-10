/** Coordinates in the input unit (millimetres by default). */
export type ParasolidPoint = readonly [number, number, number]
export type ParasolidPolygon = readonly ParasolidPoint[]
export type ParasolidPolygons = readonly ParasolidPolygon[]
/** Native Parasolid RGB values, each in [0, 1]. Alpha is not supported. */
export type ParasolidColor = readonly [number, number, number]

export interface ParasolidWriteOptions {
  /** Input units. Parasolid stores geometry in metres. */
  units?: "mm" | "m"
  /** Reserved for future name attributes; names are not transmitted yet. */
  name?: string
  /** Default RGB color, attached to the body and inherited by its faces. */
  color?: ParasolidColor
  /** Optional face overrides in polygon order; undefined inherits body color. */
  faceColors?: readonly (ParasolidColor | undefined)[]
}

/** A trimmed planar face: outer boundary first, followed by hole boundaries. */
export interface ParasolidPlanarFace {
  loops: ParasolidPolygons
}

interface ParasolidBodyAttributes {
  /** Reserved for future name attributes; names are not transmitted yet. */
  name?: string
  color?: ParasolidColor
  /** One entry per supplied polygon or explicit face; undefined inherits body color. */
  faceColors?: readonly (ParasolidColor | undefined)[]
}

/** Supply polygon faces or explicit multi-loop faces, never both. */
export type ParasolidBodyInput = ParasolidBodyAttributes &
  (
    | { polygons: ParasolidPolygons; faces?: never }
    | { faces: readonly ParasolidPlanarFace[]; polygons?: never }
  )

export type Point = [number, number, number]

export interface PreparedMesh {
  points: Point[]
  boundaries: number[][][]
}
