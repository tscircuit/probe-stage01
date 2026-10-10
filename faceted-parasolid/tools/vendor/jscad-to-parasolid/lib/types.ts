import type { JscadOperation } from "jscad-planner"

export type Point3 = readonly [number, number, number]
export type ParasolidColorInput = string | readonly number[]
export type ParasolidRgbColor = readonly [number, number, number]

/** Also accepts JSON-exported JSCAD vertices and typed coordinate arrays. */
export type Geom3Vertex =
  | ArrayLike<number>
  | { readonly pos: ArrayLike<number> }
  | { readonly position: ArrayLike<number> }

export interface Geom3Like {
  readonly polygons: readonly {
    readonly vertices: readonly Geom3Vertex[]
    readonly color?: ParasolidColorInput
  }[]
  /** JSCAD's column-major, lazily applied affine matrix. */
  readonly transforms?: ArrayLike<number>
  readonly color?: ParasolidColorInput
}

export type JscadGeometryInput = JscadOperation | Geom3Like

/** The vanilla renderer can use either jscad-planner or @jscad/modeling. */
export interface RenderedModel {
  readonly geometries: readonly {
    readonly geom: JscadGeometryInput
    readonly color?: ParasolidColorInput
    readonly name?: string
  }[]
}

export type JscadToParasolidInput =
  | JscadGeometryInput
  | readonly JscadGeometryInput[]
  | RenderedModel

export interface JscadToParasolidOptions {
  /** Merge adjacent coplanar CAD faces. Default true; curves remain faceted. */
  readonly mergeCoplanarFaces?: boolean
  /** Input length unit. X_T coordinates are always written in metres. */
  readonly units?: "mm" | "m"
  /** Reserved for future X_T name attributes; not transmitted yet. */
  readonly name?: string
}

export interface ParasolidBodyInput {
  readonly polygons: readonly (readonly Point3[])[]
  readonly name?: string
  readonly color?: ParasolidRgbColor
  readonly faceColors?: readonly (ParasolidRgbColor | undefined)[]
}
