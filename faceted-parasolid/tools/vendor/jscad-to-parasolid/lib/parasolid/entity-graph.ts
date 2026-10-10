import { Entity, EntityReference } from "parasolidts"

/** Assign IDs as entities are created so references may precede their targets. */
export function createEntityGraph() {
  const entities: Entity[] = []
  const add = <T extends Entity>(entity: T): T => {
    entity.id = entities.length + 1
    entities.push(entity)
    return entity
  }
  return { entities, add }
}

export type EntityGraph = ReturnType<typeof createEntityGraph>

export const ref = <T extends Entity>(
  entity: T | undefined,
): EntityReference<T> | null =>
  entity ? new EntityReference<T>(entity.id) : null

export const configure = <T extends Entity>(
  entity: T,
  properties: Partial<T>,
) => Object.assign(entity, properties)
