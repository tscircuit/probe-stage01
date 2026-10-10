import { Repository, Body } from "parasolidts"
import type {
  ParasolidBodyInput,
  ParasolidWriteOptions,
} from "./parasolid/types"
import { inputScale } from "./parasolid/normalize-polygons"
import { prepareMesh } from "./parasolid/prepare-mesh"
import { createEntityGraph } from "./parasolid/entity-graph"
import { buildBodyTopology } from "./parasolid/build-body-topology"
import { createBodyColorWriter, validateColor } from "./parasolid/body-colors"

/** Converter-owned topology construction; the parser only serializes entities. */
export function buildParasolidRepository(
  bodies: readonly ParasolidBodyInput[],
  options: Pick<ParasolidWriteOptions, "units"> = {},
): Repository {
  if (bodies.length === 0)
    throw new Error("At least one solid body is required")
  const scale = inputScale(options)
  const graph = createEntityGraph()
  const writeColors = createBodyColorWriter(graph)
  const bodyNodes = bodies.map(() => graph.add(new Body()))
  bodies.forEach((input, bodyIndex) => {
    validateColor(input.color)
    if ((input.polygons === undefined) === (input.faces === undefined))
      throw new Error(
        "A body must supply either polygons or explicit faces, not both",
      )
    const inputFaces =
      input.faces ?? input.polygons!.map((polygon) => ({ loops: [polygon] }))
    if (input.faceColors !== undefined) {
      if (
        !Array.isArray(input.faceColors) ||
        input.faceColors.length !== inputFaces.length
      )
        throw new Error(
          "faceColors must have one entry per input polygon or face",
        )
      input.faceColors.forEach(validateColor)
    }
    const mesh = prepareMesh(inputFaces, scale)
    const body = bodyNodes[bodyIndex]!
    const faces = buildBodyTopology(
      graph,
      body,
      mesh,
      bodyNodes[bodyIndex - 1],
      bodyNodes[bodyIndex + 1],
    )
    writeColors(body, faces, input)
  })
  return new Repository({ entities: graph.entities })
}
