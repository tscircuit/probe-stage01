import { jscadToParasolid } from './vendor/jscad-to-parasolid/lib/index.ts'

const [input, output] = process.argv.slice(2)
if (!input || !output) throw new Error('Usage: export_mesh.ts mesh.json output.faceted.x_t')
const source = await Bun.file(input).json()
const polygons = source.triangles.map((triangle: number[]) => ({
  vertices: triangle.map((index: number) => source.vertices[index]),
}))
const start = performance.now()
const xt = jscadToParasolid({ polygons }, { units: 'mm', name: source.name })
await Bun.write(output, xt)
console.log(JSON.stringify({ name:source.name, seconds:(performance.now()-start)/1000, bytes:xt.length, triangles:polygons.length }))
