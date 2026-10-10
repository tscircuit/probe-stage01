import {
  Body,
  Region,
  Shell,
  Vertex,
  Point as NativePoint,
  Face,
  Loop,
  Plane,
  Edge,
  Line,
  Fin,
  Vector3,
} from "parasolidts"
import { ref, configure, type EntityGraph } from "./entity-graph"
import type { PreparedMesh } from "./types"
import { edgeKey, normalOf, sub, unit } from "./mesh-math"

interface MeshEdge {
  start: number
  end: number
  fins: number[]
  node: Edge
  curve: Line
}
interface MeshFin {
  start: number
  end: number
  edge: MeshEdge
  node: Fin
}

/** Build one closed body's native topology and its point/line/plane geometry. */
export function buildBodyTopology(
  graph: EntityGraph,
  body: Body,
  mesh: PreparedMesh,
  previousBody: Body | undefined,
  nextBody: Body | undefined,
): Face[] {
  const { add, entities } = graph
  const { points, boundaries } = mesh
  const cycles = boundaries.map((rings) => rings[0]!)
  const solid = add(new Region({ regionKind: "S", bodyRef: ref(body) }))
  const exterior = add(
    new Region({
      regionKind: "V",
      bodyRef: ref(body),
      nextRegion: ref(solid),
    }),
  )
  // XT requires the region-chain head to be the infinite exterior void.
  solid.previousRegion = ref(exterior)
  const backShell = add(
    new Shell({ legacyBody: ref(body), regionRef: ref(solid) }),
  )
  const frontShell = add(new Shell({ regionRef: ref(exterior) }))
  solid.shellHead = ref(backShell)
  exterior.shellHead = ref(frontShell)
  for (const entity of [solid, exterior, backShell, frontShell])
    entity.localId = entity.id
  const vertices = points.map(() =>
    add(new Vertex({ precision: null, ownerRef: ref(body) })),
  )
  const pointNodes = points.map((position) =>
    add(new NativePoint({ position: new Vector3(position) })),
  )
  const faces = cycles.map(() =>
    add(
      new Face({
        precision: null,
        backShell: ref(backShell),
        frontShell: ref(frontShell),
      }),
    ),
  )
  const loops = boundaries.map((rings, i) =>
    rings.map(() => add(new Loop({ faceRef: ref(faces[i]) }))),
  )
  const planes = cycles.map(() => add(new Plane()))
  const edges: MeshEdge[] = []
  const edgeMap = new Map<string, MeshEdge>()
  const fins: MeshFin[] = []
  const vertexFins = points.map(() => [] as number[])
  const faceFins = boundaries.map((rings) =>
    rings.map((cycle) =>
      cycle.map((start, i) => {
        const end = cycle[(i + 1) % cycle.length]!
        const key = edgeKey(start, end)
        let edge = edgeMap.get(key)
        if (!edge) {
          edge = {
            start,
            end,
            fins: [],
            node: add(new Edge({ precision: null, ownerRef: ref(body) })),
            curve: add(new Line()),
          }
          edgeMap.set(key, edge)
          edges.push(edge)
        }
        const fin = { start, end, edge, node: add(new Fin()) }
        const index = fins.length
        fins.push(fin)
        edge.fins.push(index)
        vertexFins[end]!.push(index)
        return index
      }),
    ),
  )
  configure(body, {
    minLocalId: body.id,
    maxLocalId: entities.length,
    sizePrecision: 1e3,
    linearPrecision: 1e-8,
    storageState: 1,
    bodyKind: 1,
    // XT nominal geometry state must be 1 for externally written bodies.
    geometryState: 1,
    nextBody: ref(nextBody),
    previousBody: ref(previousBody),
    legacyShell: ref(backShell),
    boundarySurfaces: ref(planes[0]),
    boundaryCurves: ref(edges[0]!.curve),
    boundaryPoints: ref(pointNodes[0]),
    regionHead: ref(exterior),
    edgeHead: ref(edges[0]!.node),
    vertexHead: ref(vertices[0]),
  })
  backShell.backFaces = ref(faces[0])
  frontShell.frontFaces = ref(faces[0])
  points.forEach((_, i) => {
    const vertex = vertices[i]!
    const point = pointNodes[i]!
    configure(vertex, {
      localId: vertex.id,
      finHead: ref(fins[vertexFins[i]![0]!]!.node),
      previousVertex: ref(vertices[i - 1]),
      nextVertex: ref(vertices[i + 1]),
      pointRef: ref(point),
    })
    configure(point, {
      localId: point.id,
      ownerRef: ref(vertex),
      nextPoint: ref(pointNodes[i + 1]),
      previousPoint: ref(pointNodes[i - 1]),
    })
  })
  cycles.forEach((cycle, i) => {
    const face = faces[i]!
    const faceLoops = loops[i]!
    const plane = planes[i]!
    const next = ref(faces[i + 1])
    const previous = ref(faces[i - 1])
    configure(face, {
      localId: face.id,
      nextBack: next,
      previousBack: previous,
      loopHead: ref(faceLoops[0]),
      surfaceRef: ref(plane),
      nextFront: next,
      previousFront: previous,
    })
    const rings = faceFins[i]!
    faceLoops.forEach((loop, j) => {
      loop.localId = loop.id
      loop.finRef = ref(fins[rings[j]![0]!]!.node)
      loop.nextLoop = ref(faceLoops[j + 1])
    })
    const origin = points[cycle[0]!]!
    configure(plane, {
      localId: plane.id,
      ownerRef: ref(face),
      nextSurface: ref(planes[i + 1]),
      previousSurface: ref(planes[i - 1]),
      origin: new Vector3(origin),
      normal: new Vector3(normalOf(cycle, points)),
      xDirection: new Vector3(unit(sub(points[cycle[1]!]!, origin))),
    })
    rings.forEach((ring, loopIndex) => {
      ring.forEach((finIndex, j) => {
        const fin = fins[finIndex]!
        const atVertex = vertexFins[fin.end]!
        const nextAtVertex = atVertex[atVertex.indexOf(finIndex) + 1]
        const other = fin.edge.fins.find((index) => index !== finIndex)!
        configure(fin.node, {
          loopRef: ref(faceLoops[loopIndex]),
          forwardFin: ref(fins[ring[(j + 1) % ring.length]!]!.node),
          backwardFin: ref(
            fins[ring[(j + ring.length - 1) % ring.length]!]!.node,
          ),
          endVertex: ref(vertices[fin.end]),
          radialFin: ref(fins[other]!.node),
          edgeRef: ref(fin.edge.node),
          nextVertexFin: ref(
            nextAtVertex === undefined ? undefined : fins[nextAtVertex]!.node,
          ),
          orientation: fin.start === fin.edge.start ? "+" : "-",
        })
      })
    })
  })
  edges.forEach((edge, i) => {
    configure(edge.node, {
      localId: edge.node.id,
      finRef: ref(fins[edge.fins[0]!]!.node),
      previousEdge: ref(edges[i - 1]?.node),
      nextEdge: ref(edges[i + 1]?.node),
      curveRef: ref(edge.curve),
    })
    configure(edge.curve, {
      localId: edge.curve.id,
      ownerRef: ref(edge.node),
      nextCurve: ref(edges[i + 1]?.curve),
      previousCurve: ref(edges[i - 1]?.curve),
      origin: new Vector3(points[edge.start]!),
      tangent: new Vector3(unit(sub(points[edge.end]!, points[edge.start]!))),
    })
  })
  return faces
}
