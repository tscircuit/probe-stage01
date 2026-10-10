import {
  Body,
  Face,
  AttributeIdentifier,
  AttributeDefinition,
  Attribute,
  RealArray,
  PointerList,
  PointerListBlock,
} from "parasolidts"
import { ref, configure, type EntityGraph } from "./entity-graph"
import type { ParasolidBodyInput, ParasolidColor } from "./types"

export const validateColor = (color: ParasolidColor | undefined) => {
  if (color === undefined) return
  if (
    !Array.isArray(color) ||
    color.length !== 3 ||
    ![...color].every(
      (channel) => Number.isFinite(channel) && channel >= 0 && channel <= 1,
    )
  )
    throw new Error(
      "Color must contain exactly three finite RGB channels in [0, 1]; alpha is not supported",
    )
}

/** Keep native color definitions shared across all bodies in the repository. */
export function createBodyColorWriter(graph: EntityGraph) {
  const { add, entities } = graph
  const definitions = new Map<8001 | 8040, AttributeDefinition>()
  const colorDefinition = (kind: 8001 | 8040): AttributeDefinition => {
    const existing = definitions.get(kind)
    if (existing) return existing
    const identifier = add(
      new AttributeIdentifier({
        value: kind === 8001 ? "SDL/TYSA_COLOUR" : "SDL/TYSA_COLOUR_2",
      }),
    )
    const definition = add(
      new AttributeDefinition({
        identifierRef: ref(identifier),
        kindId: kind,
        valueKinds: [2],
        allowedOwners: Array.from({ length: 14 }, (_, index) =>
          kind === 8001 ? index === 4 || index === 6 : index <= 2,
        ),
      }),
    )
    const previous = [...definitions.values()].at(-1)
    if (previous) previous.nextDefinition = ref(definition)
    definitions.set(kind, definition)
    return definition
  }
  return (body: Body, faces: Face[], input: ParasolidBodyInput): void => {
    const chains = new Map<8001 | 8040, Attribute[]>()
    const attachColor = (
      owner: Body | Face,
      kind: 8001 | 8040,
      color: ParasolidColor,
    ) => {
      const definition = colorDefinition(kind)
      const values = add(new RealArray({ values: [...color] }))
      const attribute = add(
        new Attribute({
          definitionRef: ref(definition),
          ownerRef: ref(owner),
          valueArrays: [ref(values)],
        }),
      )
      attribute.localId = attribute.id
      owner.annotations = ref(attribute)
      const chain = chains.get(kind) ?? []
      const previous = chain.at(-1)
      if (previous) {
        previous.nextSameKind = ref(attribute)
        attribute.previousSameKind = ref(previous)
      }
      chain.push(attribute)
      chains.set(kind, chain)
    }
    if (input.color) attachColor(body, 8040, input.color)
    faces.forEach((face, index) => {
      const color = input.faceColors?.[index] ?? input.color
      if (color) attachColor(face, 8001, color)
    })
    if (chains.size > 0) {
      const heads = [...chains.values()].map((chain) => ref(chain[0]))
      const list = add(new PointerList())
      const block = add(
        new PointerListBlock({
          entries: [...heads, ...Array<null>(20 - heads.length).fill(null)],
        }),
      )
      block.usedCount = heads.length
      configure(list, {
        transmissionFlag: false,
        ownerRef: ref(body),
        entryCount: heads.length,
        blockCapacity: 20,
        cursorIndex: 1,
        cursorBlock: ref(block),
        firstBlock: ref(block),
      })
      body.attributeLists = ref(list)
      body.maxLocalId = entities.length
    }
  }
}
