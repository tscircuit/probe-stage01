import * as THREE from 'three';
import { OrbitControls } from './assets/vendor/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const viewport = $('viewport');
const canvas = $('modelCanvas');
const state = { parts: [], selected: null, hidden: new Set(), isolate: false, edges: false, ghost: false, playing: false, travel: 0, explode: 0, direction: 1, ready: false, lastTime: 0, pointer: null, hover: null, cameraView: 'iso', opticalKeepout: false, controllerReservation: true };
let model, manifest, scene, renderer, camera, controls, mechanism, contextGroup, opticalGroup, opticalReference, controllerReference, bounds, baseDistance = 300;
let kinematics = {}, meshObjects = [], selectionEdge, pose = {}, strokeMax = 40;
let catalog, activeBundle, activeVersion, loadController, loadToken = 0, resizeObserver, animationFrame, retryVersionId;
const modelMotionTags = new Set(['fixed', 'fixed_world', 'wheel', 'pinion', 'rod', 'slider', 'crank_pivot', 'slider_pivot']);
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const eyeIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
const hiddenIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 3 18 18M9.5 5.3A12 12 0 0 1 12 5c6.5 0 10 7 10 7a20 20 0 0 1-3 3.8M6 6A21 21 0 0 0 2 12s3.5 7 10 7c1.7 0 3.3-.5 4.6-1.2"/></svg>';
const humanize = (name) => name.replace(/_/g, ' ').replace(/\bzz\b/ig, 'ZZ').replace(/\bnema17\b/ig, 'NEMA17').replace(/\b625zz\b/ig, '625ZZ').replace(/\bm5\b/ig, 'M5').replace(/\bm3\b/ig, 'M3').replace(/^\w/, (s) => s.toUpperCase());
const colorString = (color) => Array.isArray(color) ? new THREE.Color(color[0], color[1], color[2]).getStyle() : (color || '#7c9b8e');
const clamp = THREE.MathUtils.clamp;
const deg = THREE.MathUtils.degToRad;
function versionURL(path, version = activeVersion) {
  if (typeof path !== 'string' || !version) return null;
  try {
    const base = new URL(version.base, document.baseURI), url = new URL(path.trim(), base);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== location.origin || url.username || url.password || !url.pathname.startsWith(base.pathname)) return null;
    return url.href;
  } catch { return null; }
}

function facetedURL(path, version = activeVersion) {
  if (typeof path !== 'string' || !version) return null;
  try {
    const allowed = new URL(`./faceted-parasolid/${version.id}/`, document.baseURI), url = new URL(path.trim(), document.baseURI);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== location.origin || url.username || url.password || !url.pathname.startsWith(allowed.pathname)) return null;
    return url.href;
  } catch { return null; }
}

function validatedFacetedAddon(version, versionManifest) {
  const addon = version?.facetedXt;
  if (!addon || !/^[a-f0-9]{64}$/.test(addon.source_sha256) || addon.source_sha256 !== versionManifest?.source_sha256 || !Array.isArray(addon.names) || !addon.names.length) return null;
  const base = facetedURL(addon.base, version);
  if (!base || !new URL(base).pathname.endsWith('/')) return null;
  return { ...addon, base };
}

function toast(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(toast.timeout);
  toast.timeout = setTimeout(() => $('toast').hidden = true, 2600);
}

function linkDownload(id, path, kind = 'version') {
  const element = $(id);
  const safe = kind === 'faceted' ? facetedURL(path) : versionURL(path);
  if (safe) { element.href = safe; element.classList.remove('disabled'); element.removeAttribute('aria-disabled'); element.hidden = false; }
  else { element.removeAttribute('href'); element.classList.add('disabled'); element.setAttribute('aria-disabled', 'true'); }
}

function metadataFor(part, versionManifest = manifest, versionModel = model, version = activeVersion) {
  const entries = versionManifest?.parts || {};
  const entry = Array.isArray(entries) ? entries.find((item) => item.name === part.name || item.id === part.name) : entries[part.name];
  const category = entry?.category || (part.motion === 'fixed_world' || part.reference || /reference/i.test(part.name) ? 'References' : versionModel?.meta?.printable?.includes(part.name) ? 'Fabricated parts' : 'Hardware');
  const addon = validatedFacetedAddon(version, versionManifest), nativeXt = entry?.xt || entry?.xtUrl;
  const unsupportedReason = typeof addon?.unsupported?.[part.name] === 'string' ? addon.unsupported[part.name] : null;
  const facetedXt = !nativeXt && addon?.names.includes(part.name) ? facetedURL(new URL(`${encodeURIComponent(part.name)}.faceted.x_t`, addon.base).href, version) : null;
  return { ...entry, name: part.name, title: entry?.title || part.title || humanize(part.name), category, description: entry?.description || part.description, dimensions: entry?.dimensions || part.dimensions, quantity: entry?.quantity || part.quantity, material: typeof entry?.material === 'string' ? entry.material : null, step: entry?.step || entry?.stepUrl, xt: nativeXt || facetedXt, xtKind: nativeXt ? 'exact' : facetedXt ? 'faceted' : unsupportedReason ? 'faceted_unavailable' : null, xtUnavailableReason: unsupportedReason };
}

function buildPartList() {
  const fragment = document.createDocumentFragment();
  const filter = $('partSearch').value.trim().toLowerCase();
  const groups = ['Fabricated parts', 'Hardware', 'References'];
  for (const part of state.parts) if (!groups.includes(part.meta.category)) groups.push(part.meta.category);
  let matches = 0;
  for (const category of groups) {
    const parts = state.parts.filter((part) => part.meta.category === category && (part.meta.title + ' ' + part.name).toLowerCase().includes(filter));
    if (!parts.length) continue;
    const heading = document.createElement('div');
    heading.className = 'part-group-label';
    const headingName = document.createElement('span'); headingName.textContent = category;
    const headingCount = document.createElement('span'); headingCount.textContent = parts.length;
    heading.append(headingName, headingCount); fragment.append(heading);
    for (const part of parts) {
      matches++;
      const row = document.createElement('div');
      row.className = 'part-row'; row.dataset.part = part.name; row.setAttribute('role', 'listitem');
      row.classList.toggle('selected', state.selected === part);
      row.classList.toggle('is-hidden', !part.object.visible);
      const select = document.createElement('button'); select.className = 'part-select'; select.setAttribute('aria-pressed', String(state.selected === part)); select.title = part.meta.title;
      const swatch = document.createElement('span'); swatch.className = 'part-swatch'; swatch.style.background = colorString(part.color); swatch.setAttribute('aria-hidden', 'true');
      const title = document.createElement('span'); title.textContent = part.meta.title;
      select.append(swatch, title); select.addEventListener('click', () => selectPart(part));
      const visibility = document.createElement('button'); visibility.className = 'part-visibility'; visibility.innerHTML = part.object.visible ? eyeIcon : hiddenIcon;
      visibility.setAttribute('aria-label', (part.object.visible ? 'Hide ' : 'Show ') + part.meta.title); visibility.title = (part.object.visible ? 'Hide ' : 'Show ') + part.meta.title;
      visibility.addEventListener('click', () => togglePart(part));
      row.append(select, visibility); fragment.append(row); part.row = row;
    }
  }
  if (!matches) { const empty = document.createElement('p'); empty.className = 'empty-parts'; empty.textContent = 'No components match your search.'; fragment.append(empty); }
  $('partList').replaceChildren(fragment);
  $('partCount').textContent = `${state.parts.length} components · millimeters`;
  updateCollisionRows();
}

function updateVisibility() {
  for (const part of state.parts) part.object.visible = !state.hidden.has(part.name) && (!state.isolate || part === state.selected);
  buildPartList();
  $('showAll').textContent = state.isolate ? 'Exit isolate' : 'Show all';
  $('isolate').textContent = state.isolate ? 'Exit isolate' : 'Isolate part';
  $('isolate').setAttribute('aria-pressed', String(state.isolate));
  $('modelStatus').textContent = state.isolate && state.selected ? state.selected.meta.title + ' · isolated' : `${state.parts.filter((p) => p.object.visible).length} of ${state.parts.length} components visible`;
  setControllerReservation(state.controllerReservation);
}

function togglePart(part) {
  if (state.isolate) { state.isolate = false; state.hidden = new Set(state.parts.filter((p) => !p.object.visible).map((p) => p.name)); }
  if (state.hidden.has(part.name)) state.hidden.delete(part.name); else state.hidden.add(part.name);
  updateVisibility();
}

function selectPart(part) {
  if (!part || !state.parts.includes(part)) return;
  state.selected = part;
  $('selectedName').textContent = part.meta.title;
  $('partDetails').querySelector('.detail-eyebrow').textContent = part.meta.category.toUpperCase();
  $('selectedDescription').textContent = part.meta.description || defaultDescription(part);
  $('isolate').disabled = false; $('focusPart').disabled = false;
  const info = document.createDocumentFragment();
  for (const text of [part.meta.dimensions, part.meta.quantity ? `Qty ${part.meta.quantity}` : null, part.meta.material].filter(Boolean)) {
    const label = document.createElement('span'); label.textContent = typeof text === 'object' ? JSON.stringify(text) : text; info.append(label);
  }
  $('selectedMeta').replaceChildren(info);
  linkDownload('stepDownload', part.meta.step || part.meta.stepUrl);
  linkDownload('xtDownload', part.meta.xt || part.meta.xtUrl, part.meta.xtKind === 'faceted' ? 'faceted' : 'version');
  $('xtFormatLabel').textContent = part.meta.xtKind?.startsWith('faceted') ? 'Faceted x_t' : 'x_t';
  $('xtDownload').querySelector('.unavailable-tag').hidden = Boolean(part.meta.xt || part.meta.xtUrl);
  $('exportNote').textContent = part.meta.xtKind === 'faceted' ? 'Faceted x_t approximates curves with flat faces. STEP preserves exact geometry. Native Siemens import is unverified.' : part.meta.xt || part.meta.xtUrl ? 'Solid CAD files for this component.' : part.meta.xtUnavailableReason || 'No x_t file is available for this component. Exact STEP is available.';
  updateAppearance();
  updateVisibility();
}

function defaultDescription(part) {
  if (part.motion === 'fixed_world') return 'Reference geometry to inspect the microscope and specimen clearance.';
  if (/strut|brace/i.test(part.name)) return 'Triangulated support to stiffen the frame at the microscope end.';
  if (/wheel|gear|sector_crank/i.test(part.name)) return 'Crank wheel with internal teeth along a 180° slot.';
  if (/pinion/i.test(part.name)) return 'NEMA17 drive pinion engaging the inner gear sector.';
  if (/clamp/i.test(part.name)) return 'Split mounting clamp around the 44 mm microscope cylinder.';
  if (/probe|holder/i.test(part.name)) return '6 mm probe mount at 60° above the specimen plate.';
  if (/bearing/i.test(part.name)) return '625ZZ bearing, 5 mm bore × 16 mm outside diameter × 5 mm wide.';
  if (/rod/i.test(part.name)) return 'Connecting link between the crank and the vertical carriage.';
  if (/slider|carriage/i.test(part.name)) return 'Guided carriage providing 40 mm of straight vertical mechanical travel.';
  if (/nema|motor/i.test(part.name)) return 'NEMA17 stepper motor reference with M3 mounting screws.';
  if (/bolt|nut|washer/i.test(part.name)) return 'Assembly hardware; inspect the solid model for size and placement.';
  return 'Select, isolate or download this assembly component.';
}

function initScene() {
  scene = new THREE.Scene();
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  camera = new THREE.PerspectiveCamera(34, 1, 0.5, 4000);
  camera.up.set(0, 1, 0);
  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true; controls.dampingFactor = 0.085;
  controls.rotateSpeed = 0.68; controls.panSpeed = 0.7; controls.zoomSpeed = 0.8;
  controls.minDistance = 25; controls.maxDistance = 1600;
  controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE; controls.mouseButtons.MIDDLE = THREE.MOUSE.DOLLY; controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
  controls.addEventListener('start', () => { state.cameraView = 'custom'; setControllerReservation(state.controllerReservation); document.querySelectorAll('[data-view]').forEach((button) => { button.classList.remove('active'); button.setAttribute('aria-pressed', 'false'); }); });
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb1c0ac, 2.0));
  const key = new THREE.DirectionalLight(0xfffdf3, 3.1); key.position.set(-200, 340, 330); scene.add(key);
  const rim = new THREE.DirectionalLight(0xc2dce8, 1.4); rim.position.set(230, 80, -250); scene.add(rim);
  const fill = new THREE.DirectionalLight(0xf2fff8, 0.75); fill.position.set(160, -100, 260); scene.add(fill);
  resize(); resizeObserver = new ResizeObserver(resize); resizeObserver.observe(viewport);
}

function resize() {
  if (!renderer) return;
  const width = viewport.clientWidth, height = viewport.clientHeight;
  if (!width || !height) return;
  renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
  if (state.ready && state.cameraView === 'microscope') setOpticalCamera();
}

function normalizedKinematics(meta) {
  const value = { crank_radius: 25, rod_length: 100, phi_min: -Math.asin(.8), phi_max: Math.asin(.8), pinion_ratio: 6, pinion_center: [-50, 0, 0], ...meta.kinematics };
  value.crank_radius = meta.crank_radius ?? meta.crankRadius ?? value.crank_radius;
  value.rod_length = meta.rod_length ?? meta.rodLength ?? value.rod_length;
  value.phi_min = meta.phi_min_rad ?? value.phi_min;
  value.phi_max = meta.phi_max_rad ?? value.phi_max;
  value.pinion_ratio = meta.pinion_ratio ?? meta.ratio ?? value.pinion_ratio;
  value.pinion_center = meta.pinion_center ?? meta.pinionCenter ?? value.pinion_center;
  if (meta.limitDegrees && meta.kinematics?.phi_min === undefined) { value.phi_min = -deg(meta.limitDegrees); value.phi_max = deg(meta.limitDegrees); }
  if (value.angle_units === 'degrees' || Math.abs(value.phi_min) > Math.PI || Math.abs(value.phi_max) > Math.PI) { value.phi_min = deg(value.phi_min); value.phi_max = deg(value.phi_max); }
  for (const key of ['crank_radius', 'rod_length', 'phi_min', 'phi_max', 'pinion_ratio']) value[key] = Number(value[key]);
  if (![value.crank_radius, value.rod_length, value.phi_min, value.phi_max, value.pinion_ratio].every(Number.isFinite) || value.crank_radius <= 0 || value.rod_length <= value.crank_radius || value.phi_max <= value.phi_min || value.pinion_ratio <= 0) throw new Error('The motion dimensions are invalid.');
  if (Number(value.reference_phi ?? meta.reference_phi ?? 0) !== 0) throw new Error('The model uses an unsupported reference pose.');
  if (!Array.isArray(value.pinion_center) || value.pinion_center.length !== 3 || !value.pinion_center.every(Number.isFinite)) throw new Error('The drive pivot is invalid.');
  const y = (phi) => value.crank_radius * Math.sin(phi) - Math.sqrt(value.rod_length ** 2 - (value.crank_radius * Math.cos(phi)) ** 2);
  let previous = y(value.phi_min);
  for (let n = 1; n <= 40; n++) { const current = y(value.phi_min + (value.phi_max - value.phi_min) * n / 40); if (!(current > previous)) throw new Error('The stroke is not monotonic.'); previous = current; }
  value.stroke_max = Number(meta.stroke_mm ?? meta.stroke ?? meta.travel_mm ?? meta.travel ?? y(value.phi_max) - y(value.phi_min));
  if (!Number.isFinite(value.stroke_max) || Math.abs(value.stroke_max - 40) > .01 || Math.abs(y(value.phi_max) - y(value.phi_min) - value.stroke_max) > .01) throw new Error('This model must have 40 mm of vertical stroke.');
  value.samples = meta.clearance_samples || meta.pose_samples || meta.samples || [];
  return value;
}

function validateModel(candidate) {
  if (!Array.isArray(candidate.parts) || !candidate.parts.length) throw new Error('The assembly contains no display geometry.');
  const names = new Set();
  for (const part of candidate.parts) {
    if (typeof part.name !== 'string' || !part.name || names.has(part.name)) throw new Error('Component names must be unique.');
    names.add(part.name);
    if (!modelMotionTags.has(part.motion || 'fixed')) throw new Error('A component uses unsupported motion.');
    if (!Array.isArray(part.vertices) || !part.vertices.length || !part.vertices.every((vertex) => Array.isArray(vertex) && vertex.length === 3 && vertex.every(Number.isFinite))) throw new Error('A component contains invalid coordinates.');
    if (!Array.isArray(part.triangles) || !part.triangles.length || !part.triangles.every((triangle) => Array.isArray(triangle) && triangle.length === 3 && triangle.every((index) => Number.isInteger(index) && index >= 0 && index < part.vertices.length))) throw new Error('A component contains invalid faces.');
  }
}

function makeOpticalReference(meta) {
  const optical = meta.optical_keepout || {}, workingDistance = Number(meta.workingDistance || meta.working_distance_mm || 100);
  const reference = { radius: Number(optical.radius_mm || 22), top: Number(optical.barrel_end_y ?? 0), bottom: Number(optical.specimen_y ?? -workingDistance), x: Number(optical.center_x || 0), z: Number(optical.center_z || 0), workingDistance };
  if (!Object.values(reference).every(Number.isFinite) || reference.radius <= 0 || reference.top <= reference.bottom) throw new Error('The optical reference is invalid.');
  const { radius, top, bottom, x, z } = reference;
  const group = new THREE.Group(); group.name = 'Optical clearance annotation';
  const volume = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, top - bottom, 64, 1), new THREE.MeshBasicMaterial({ color: 0x4ba5b2, transparent: true, opacity: .055, side: THREE.DoubleSide, depthWrite: false }));
  volume.position.set(x, (top + bottom) / 2, z); volume.renderOrder = 2; group.add(volume);
  for (const y of [top, bottom]) {
    const points = Array.from({ length: 97 }, (_, index) => { const angle = index / 96 * Math.PI * 2; return new THREE.Vector3(x + Math.cos(angle) * radius, y, z + Math.sin(angle) * radius); });
    const ring = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineDashedMaterial({ color: 0x418d9e, transparent: true, opacity: .75, dashSize: 1.4, gapSize: .8, depthWrite: false }));
    ring.computeLineDistances(); ring.renderOrder = 3; group.add(ring);
  }
  for (const angle of [0, Math.PI / 2, Math.PI, Math.PI * 1.5]) {
    const px = x + Math.cos(angle) * radius, pz = z + Math.sin(angle) * radius;
    const edge = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(px, top, pz), new THREE.Vector3(px, bottom, pz)]), new THREE.LineDashedMaterial({ color: 0x70aab4, transparent: true, opacity: .3, dashSize: 2, gapSize: 2, depthWrite: false }));
    edge.computeLineDistances(); group.add(edge);
  }
  group.visible = false;
  return { group, reference };
}

function makeControllerReference(meta) {
  const reservation = meta.controllerReservation;
  if (!reservation) return null;
  const validPoint = (point) => Array.isArray(point) && point.length === 3 && point.every(Number.isFinite);
  const values = ['local_box_min', 'local_box_max', 'keepout_local_box_min', 'keepout_local_box_max'];
  if (!values.every((key) => validPoint(reservation[key])) || !validPoint(reservation.nominal_dimensions_mm) || !validPoint(reservation.rear_normal_world) || reservation.reference_only !== true) throw new Error('The controller reservation is invalid.');
  for (const [minKey, maxKey] of [['local_box_min', 'local_box_max'], ['keepout_local_box_min', 'keepout_local_box_max']]) {
    if (!reservation[minKey].every((value, index) => value < reservation[maxKey][index])) throw new Error('The controller reservation has invalid dimensions.');
  }
  const group = new THREE.Group(); group.name = 'Controller space annotation';
  const nominalBox = new THREE.Box3(new THREE.Vector3(...reservation.local_box_min), new THREE.Vector3(...reservation.local_box_max));
  const keepoutBox = new THREE.Box3(new THREE.Vector3(...reservation.keepout_local_box_min), new THREE.Vector3(...reservation.keepout_local_box_max));
  const center = nominalBox.getCenter(new THREE.Vector3());
  const volume = new THREE.Mesh(new THREE.BoxGeometry(...nominalBox.getSize(new THREE.Vector3()).toArray()), new THREE.MeshBasicMaterial({ color: 0xa57a41, transparent: true, opacity: .09, depthWrite: false, side: THREE.DoubleSide }));
  volume.name = 'Nominal controller volume'; volume.position.copy(center); volume.renderOrder = 2; group.add(volume);
  for (const [box, color, opacity] of [[nominalBox, 0xa57a41, .8], [keepoutBox, 0xc7a06c, .38]]) {
    const wire = new THREE.Box3Helper(box, color); wire.name = box === nominalBox ? 'Nominal controller outline' : 'Controller clearance outline'; wire.material.transparent = true; wire.material.opacity = opacity; wire.material.depthWrite = false; wire.renderOrder = 3; group.add(wire);
  }
  // The arrow is an annotation of the rear's outward direction, not heatsink CAD.
  const arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), new THREE.Vector3(center.x, center.y, nominalBox.min.z), 15, 0xa57a41, 4, 2.2);
  // ArrowHelper shares default geometry; each disposable version owns its copies.
  arrow.line.geometry = arrow.line.geometry.clone(); arrow.cone.geometry = arrow.cone.geometry.clone();
  arrow.name = 'Open motor rear direction'; group.add(arrow);
  return { group, nominalBox, keepoutBox, reservation };
}

function disposeBundle(bundle) {
  if (!bundle?.root) return;
  bundle.root.removeFromParent();
  const geometries = new Set(), materials = new Set();
  bundle.root.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) if (material) materials.add(material);
  });
  geometries.forEach((geometry) => geometry.dispose()); materials.forEach((material) => material.dispose());
  bundle.root.clear(); bundle.parts.length = 0; bundle.meshes.length = 0;
}

function buildBundle(candidateModel, candidateManifest, version) {
  validateModel(candidateModel);
  const meta = candidateModel.meta || {}, motion = normalizedKinematics(meta);
  const bundle = { model: candidateModel, manifest: candidateManifest, version, kinematics: motion, root: new THREE.Group(), mechanism: new THREE.Group(), context: new THREE.Group(), parts: [], meshes: [] };
  bundle.root.name = 'Version model'; bundle.root.userData.versionId = version.id; bundle.root.add(bundle.mechanism, bundle.context);
  try {
    const transform = meta.world_transform || motion.world_transform || meta.localToWorld || {};
    const translation = transform.translation || meta.wheel_origin || [meta.wheel_origin_x || 0, meta.wheel_origin_y || 0, meta.wheel_origin_z || 0];
    if (!Array.isArray(translation) || translation.length !== 3 || !translation.every(Number.isFinite)) throw new Error('The assembly location is invalid.');
    bundle.mechanism.position.fromArray(translation);
    if (transform.quaternion) {
      if (!Array.isArray(transform.quaternion) || transform.quaternion.length !== 4 || !transform.quaternion.every(Number.isFinite)) throw new Error('The assembly rotation is invalid.');
      bundle.mechanism.quaternion.fromArray(transform.quaternion).normalize();
    } else {
      const rotations = transform.rotation_degrees || [transform.rotation_x_deg || 0, transform.rotation_y_deg || 0, transform.rotation_z_deg ?? transform.rotation_deg ?? transform.rotationZDegrees ?? meta.world_rotation_deg ?? 0];
      if (!Array.isArray(rotations) || rotations.length !== 3 || !rotations.every(Number.isFinite)) throw new Error('The assembly rotation is invalid.');
      bundle.mechanism.rotation.set(...rotations.map(deg), transform.rotation_order || 'XYZ');
    }
    for (const raw of candidateModel.parts) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(raw.vertices.flat(), 3)); geometry.setIndex(raw.triangles.flat()); geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere();
      const opacity = raw.opacity ?? (Array.isArray(raw.color) ? raw.color[3] : null) ?? 1;
      const displayColor = raw.name === 'probe_reference' ? '#5e7682' : raw.name === 'motor_pinion' ? '#79909b' : raw.color;
      const color = Array.isArray(displayColor) ? new THREE.Color(displayColor[0], displayColor[1], displayColor[2]) : new THREE.Color(displayColor || '#809d8c');
      const metal = /bearing|bolt|nut|washer|shaft|rail|probe/i.test(raw.name);
      const material = new THREE.MeshStandardMaterial({ color, roughness: metal ? .37 : .61, metalness: metal ? .48 : .06, transparent: opacity < 1, opacity, depthWrite: opacity > .5, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geometry, material), group = new THREE.Group(); group.add(mesh);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28), new THREE.LineBasicMaterial({ color: 0x42614f, transparent: true, opacity: .28, depthWrite: false })); group.add(edges); edges.visible = false; edges.renderOrder = 1;
      const part = { ...raw, color: displayColor, object: group, mesh, edges, material, baseOpacity: opacity, baseColor: color.clone(), visible: true };
      part.meta = metadataFor(part, candidateManifest, candidateModel, version); mesh.userData.part = part;
      (raw.motion === 'fixed_world' ? bundle.context : bundle.mechanism).add(group); bundle.parts.push(part); bundle.meshes.push(mesh);
    }
    const gridY = meta.specimen_plate_y ?? meta.specimen_y ?? -Number(meta.workingDistance || meta.working_distance_mm || 100);
    const grid = new THREE.GridHelper(360, 36, 0xc6d5c6, 0xd9e3d7); grid.position.set(meta.optical_center_x || 0, gridY - 1.2, 0); grid.material.transparent = true; grid.material.opacity = .34; grid.material.depthWrite = false; bundle.context.add(grid);
    const optical = makeOpticalReference(meta); bundle.opticalGroup = optical.group; bundle.opticalReference = optical.reference; bundle.root.add(optical.group);
    bundle.controllerReference = makeControllerReference(meta);
    if (bundle.controllerReference) bundle.mechanism.add(bundle.controllerReference.group);
    bundle.selectionEdge = new THREE.Group(); bundle.root.add(bundle.selectionEdge);
    return bundle;
  } catch (error) { disposeBundle(bundle); throw error; }
}

function updateComparison() {
  const comparison = manifest.comparison || activeVersion.comparison, metrics = document.createDocumentFragment();
  let count = 0;
  for (const [key, label, unit, digits] of [
    ['wheel_outer_diameter_mm', 'Wheel diameter', 'mm', 0],
    ['printed_volume_reduction_percent', 'Less printed volume', '%', 1],
    ['estimated_mass_g', 'Estimated mass', 'g', 0],
    ['gravity_moment_reduction_percent', 'Lower gravity moment', '%', 1]
  ]) {
    const value = comparison?.[key];
    if (value === undefined || value === null || !Number.isFinite(Number(value))) continue;
    const item = document.createElement('div'), name = document.createElement('span'), amount = document.createElement('strong');
    name.textContent = label; amount.textContent = `${Number(value).toFixed(digits)} ${unit}`; item.append(name, amount); metrics.append(item); count++;
  }
  $('comparisonMetrics').replaceChildren(metrics);
  $('comparisonSummary').hidden = count === 0;
  $('comparisonAssumptions').textContent = count ? `${comparison.assumptions || 'Estimates depend on the modeled materials and loads.'} Stiffness requires physical validation.` : '';
}

function captureView() {
  return { ready: state.ready, preset: state.cameraView, travel: state.travel, optical: state.opticalKeepout, controller: state.controllerReservation, position: camera?.position.clone(), target: controls?.target.clone(), up: camera?.up.clone(), fov: camera?.fov, minDistance: controls?.minDistance };
}

function installBundle(bundle, previousView) {
  const previous = activeBundle;
  activeBundle = bundle; activeVersion = bundle.version; model = bundle.model; manifest = bundle.manifest; kinematics = bundle.kinematics; strokeMax = kinematics.stroke_max;
  mechanism = bundle.mechanism; contextGroup = bundle.context; opticalGroup = bundle.opticalGroup; opticalReference = bundle.opticalReference; selectionEdge = bundle.selectionEdge;
  controllerReference = bundle.controllerReference;
  state.parts = bundle.parts; meshObjects = bundle.meshes; state.selected = null; state.hidden.clear(); state.isolate = false; state.hover = null; state.pointer = null; state.explode = 0; state.direction = 1; state.lastTime = 0; pose = {};
  $('hoverLabel').hidden = true; canvas.style.cursor = 'grab'; $('explodeSlider').value = '0'; $('explodeValue').textContent = '0%'; $('partSearch').value = '';
  scene.add(bundle.root); state.ready = true;
  $('travelSlider').max = strokeMax; $('strokeValue').textContent = strokeMax.toFixed(0); $('travelMaximum').textContent = ` / ${strokeMax.toFixed(0)} mm`;
  $('workingDistanceValue').textContent = opticalReference.workingDistance.toFixed(0);
  $('probeAngleValue').textContent = Number(model.meta?.approachAngle ?? model.meta?.probe_angle_deg ?? 60).toFixed(0);
  $('cylinderDiameterValue').textContent = Number(model.meta?.microscopeDiameter ?? model.meta?.cylinder_diameter_mm ?? 44).toFixed(0);
  $('motionDescription').textContent = `Vertical motion · fixed ${$('probeAngleValue').textContent}° probe angle`;
  $('opticalCaption').querySelector('strong').textContent = `Ø${(opticalReference.radius * 2).toFixed(0)} mm barrel projection`;
  const downloads = manifest.downloads || {};
  linkDownload('assemblyDownload', downloads.assemblyStep || downloads.assembly_step || manifest.assemblyStep); linkDownload('sourceDownload', downloads.source || manifest.source); linkDownload('bundleDownload', downloads.bundle || manifest.bundle);
  $('fitNotes').textContent = manifest.notes?.fit || `${strokeMax} mm straight vertical travel at a fixed ${$('probeAngleValue').textContent}° probe angle.`;
  $('validationNotes').textContent = manifest.notes?.validation || 'This fit and motion prototype requires physical load, deflection and print-clearance validation.';
  $('cadNotes').textContent = manifest.notes?.exports || 'STEP preserves solid geometry. x_t is unavailable without a genuine Parasolid exporter.';
  const addon = validatedFacetedAddon(activeVersion, manifest);
  if (addon) $('cadNotes').textContent = 'STEP preserves exact solid geometry. Faceted x_t approximates curves with flat faces and is available for the validated components. Native Siemens import is unverified.';
  linkDownload('facetedBundleDownload', addon?.bundle, 'faceted'); $('facetedBundleDownload').hidden = !addon?.bundle || !facetedURL(addon.bundle);
  const reportUrl = addon?.report && facetedURL(addon.report); $('facetedReportLink').hidden = !reportUrl;
  if (reportUrl) $('facetedReportLink').href = reportUrl; else $('facetedReportLink').removeAttribute('href');
  $('controllerToggle').hidden = !controllerReference;
  $('motorRearView').hidden = !controllerReference;
  $('controllerNotes').hidden = !controllerReference;
  $('controllerNotes').textContent = controllerReference ? 'The motor rear opens tangentially away from the barrel. The amber box reserves 42 × 42 × 20 mm for the controller; the outer wireframe adds 2 mm of side and rear clearance. The heatsink and controller mass are unknown and excluded from the estimates.' : '';
  const controllerCheck = controllerReference?.reservation?.verification;
  const verifiedController = /^[a-f0-9]{64}$/.test(controllerCheck?.source_sha256) && controllerCheck.source_sha256 === manifest.source_sha256 && controllerCheck.validated === true && controllerCheck.continuous === true && controllerCheck.open_rear === true;
  $('controllerVerification').hidden = !verifiedController;
  $('controllerVerification').textContent = verifiedController ? 'Reserved volume and open rear corridor verified clear through the full stroke.' : '';
  for (const [id, path] of [['controllerEnvelopeDownload', downloads.controllerEnvelope], ['controllerKeepoutDownload', downloads.controllerKeepout]]) {
    linkDownload(id, controllerReference ? path : null); $(id).hidden = !controllerReference || !versionURL(path);
  }
  const controllerReport = verifiedController && versionURL(manifest.reports?.controller);
  $('controllerReportLink').hidden = !controllerReport;
  if (controllerReport) $('controllerReportLink').href = controllerReport; else $('controllerReportLink').removeAttribute('href');
  document.querySelectorAll('.clearance-limit').forEach((element) => element.remove());
  const limit = model.meta?.safe_probe_travel_mm ?? model.meta?.clearance_limit_mm ?? manifest.clearance?.safe_travel_mm;
  if (Number.isFinite(Number(limit)) && Number(limit) > 0 && Number(limit) < strokeMax) {
    const slider = $('travelSlider'); let wrapper = slider.parentElement;
    if (!wrapper.classList.contains('travel-range-wrap')) { wrapper = document.createElement('div'); wrapper.className = 'travel-range-wrap'; slider.replaceWith(wrapper); wrapper.append(slider); }
    const marker = document.createElement('span'); marker.className = 'clearance-limit'; marker.style.left = `${Number(limit) / strokeMax * 100}%`; marker.title = `Probe clearance limit: ${Number(limit).toFixed(1)} mm`; wrapper.append(marker);
  }
  updatePose(clamp(previousView.travel, 0, strokeMax));
  bounds = new THREE.Box3(); state.parts.forEach((part) => bounds.expandByObject(part.object));
  const initial = state.parts.find((part) => /crank.*wheel|crank_gear|sector_gear|sector_crank/i.test(part.name)) || state.parts.find((part) => part.meta.category === 'Fabricated parts') || state.parts[0];
  selectPart(initial);
  if (previousView.ready && previousView.preset === 'custom') {
    state.cameraView = 'custom'; camera.position.copy(previousView.position); controls.target.copy(previousView.target); setCameraUp(previousView.up.toArray()); camera.fov = previousView.fov; camera.updateProjectionMatrix(); controls.minDistance = previousView.minDistance; controls.update();
    document.querySelectorAll('[data-view]').forEach((button) => { button.classList.remove('active'); button.setAttribute('aria-pressed', 'false'); });
  } else setCamera(previousView.ready ? previousView.preset : 'iso');
  setOpticalKeepout(previousView.optical);
  setControllerReservation(previousView.controller);
  $('versionSelect').value = activeVersion.id; $('versionLabel').textContent = activeVersion.label; $('releaseLink').href = activeVersion.release || catalog.repository; $('releaseLink').textContent = `${activeVersion.id} on GitHub ↗`;
  updateComparison();
  $('loadState').hidden = true; window.modelReady = true;
  disposeBundle(previous);
}

function setOpticalKeepout(visible) {
  state.opticalKeepout = Boolean(visible);
  if (opticalGroup) opticalGroup.visible = state.opticalKeepout;
  $('opticalKeepout').checked = state.opticalKeepout;
  $('opticalCaption').hidden = !state.opticalKeepout;
  viewport.classList.toggle('show-optical', state.opticalKeepout);
}

function setControllerReservation(visible) {
  state.controllerReservation = Boolean(visible);
  const show = Boolean(controllerReference && state.controllerReservation && state.cameraView !== 'microscope' && !state.isolate && state.explode === 0);
  if (controllerReference) controllerReference.group.visible = show;
  $('controllerSpace').checked = state.controllerReservation;
  $('controllerCaption').hidden = !show;
  viewport.classList.toggle('show-controller', show);
}

function setOpticalCamera() {
  if (!opticalReference) return;
  const { radius, top, bottom, x, z } = opticalReference;
  const distance = Math.max(1, top - bottom - .5);
  const verticalRadius = radius * 1.24 * Math.max(1, 1 / camera.aspect);
  camera.fov = clamp(THREE.MathUtils.radToDeg(2 * Math.atan(verticalRadius / distance)), 15, 110);
  camera.updateProjectionMatrix();
  controls.minDistance = Math.min(3, distance);
  controls.target.set(x, bottom, z);
  setCameraUp([0, 0, -1]);
  camera.position.set(x, top - .5, z);
  controls.update();
}

function setCameraUp(up) {
  camera.up.fromArray(up);
  // OrbitControls caches the orbit-axis basis when it is constructed. The vendored
  // controls must share the changed camera basis for the optical-axis preset.
  controls._quat.setFromUnitVectors(camera.up, new THREE.Vector3(0, 1, 0));
  controls._quatInverse.copy(controls._quat).invert();
}

function sliderY(phi) {
  const radius = Number(kinematics.crank_radius), length = Number(kinematics.rod_length);
  const cx = radius * Math.cos(phi), cy = radius * Math.sin(phi);
  return cy - Math.sqrt(Math.max(0, length * length - cx * cx));
}

function phiFromTravel(travel) {
  let low = Number(kinematics.phi_min), high = Number(kinematics.phi_max);
  const target = sliderY(low) + travel;
  for (let n = 0; n < 35; n++) { const mid = (low + high) / 2; if (sliderY(mid) < target) low = mid; else high = mid; }
  return (low + high) / 2;
}

function translationMatrix(x, y, z) { return new THREE.Matrix4().makeTranslation(x, y, z); }
function pivotRotation(angle, center) {
  return translationMatrix(...center).multiply(new THREE.Matrix4().makeRotationZ(angle)).multiply(translationMatrix(-center[0], -center[1], -center[2]));
}

function updatePose(travel) {
  if (!state.ready) return;
  state.travel = clamp(Number(travel), 0, strokeMax);
  const phi = phiFromTravel(state.travel), radius = Number(kinematics.crank_radius), length = Number(kinematics.rod_length);
  const cx = radius * Math.cos(phi), cy = radius * Math.sin(phi), sy = sliderY(phi), sy0 = sliderY(0);
  const rodangle = -Math.asin(cx / length), rodangle0 = -Math.asin(radius / length);
  const origin = kinematics.pinion_center || [-50, 0, 0];
  const crankOrigin = [radius, 0, 0];
  for (const part of state.parts) {
    let matrix = new THREE.Matrix4();
    switch (part.motion) {
      case 'wheel': matrix.makeRotationZ(phi); break;
      case 'pinion': matrix.copy(pivotRotation((kinematics.pinion_ratio || 6) * phi, origin)); break;
      case 'rod': matrix.copy(translationMatrix(cx - radius, cy, 0).multiply(pivotRotation(rodangle - rodangle0, crankOrigin))); break;
      case 'slider': case 'slider_pivot': matrix.makeTranslation(0, sy - sy0, 0); break;
      case 'crank_pivot': matrix.makeTranslation(cx - radius, cy, 0); break;
      default: break;
    }
    if (state.explode > 0) {
      const vector = part.explode || explosionVector(part);
      matrix.premultiply(translationMatrix(vector[0] * state.explode, vector[1] * state.explode, vector[2] * state.explode));
    }
    part.object.matrixAutoUpdate = false; part.object.matrix.copy(matrix); part.object.matrixWorldNeedsUpdate = true;
  }
  mechanism.updateMatrixWorld(true); contextGroup.updateMatrixWorld(true);
  setControllerReservation(state.controllerReservation);
  pose = { phi, cx, cy, sy, travel: state.travel };
  $('travelSlider').value = state.travel;
  $('travelSlider').style.setProperty('--progress', `${state.travel / strokeMax * 100}%`);
  $('travelSlider').setAttribute('aria-valuetext', `${state.travel.toFixed(1)} millimeters above the lowest position`);
  $('travelValue').textContent = state.travel.toFixed(1);
  updateClearance();
}

function explosionVector(part) {
  if (part.motion === 'fixed_world') return [0, 0, 0];
  const center = part.mesh.geometry.boundingBox.getCenter(new THREE.Vector3());
  if (/clamp/i.test(part.name)) return [center.x > 0 ? 18 : -18, 5, center.z > 0 ? 15 : -15];
  if (/motor|nema17/i.test(part.name)) return [-22, 0, -30];
  if (part.motion === 'wheel') return [0, 0, 30];
  if (part.motion === 'pinion') return [-10, 0, 40];
  if (part.motion === 'rod' || /rod/i.test(part.name)) return [12, 0, 53];
  if (part.motion === 'slider' || part.motion === 'slider_pivot') return [28, -3, 24];
  if (/strut|brace/i.test(part.name)) return [Math.sign(center.x) * 22, 8, Math.sign(center.z) * 20];
  if (/bearing|bolt|nut|washer/i.test(part.name)) return [Math.sign(center.x) * 9, 0, (center.z >= 0 ? 1 : -1) * 38];
  return [Math.sign(center.x) * 12, 0, Math.sign(center.z || 1) * 20];
}

function clearanceAt(travel) {
  const meta = model.meta || {}, samples = kinematics.samples || [];
  const intervals = meta.clearance_intervals || meta.clearance?.intervals || manifest.clearance_intervals || manifest.clearance?.intervals;
  if (Array.isArray(intervals)) {
    const interval = intervals.find((item) => travel >= Number(item.min_mm) && (travel < Number(item.max_mm) || (Number(item.max_mm) === strokeMax && travel <= strokeMax)));
    if (!interval) return { collision: null, parts: [], detail: 'This position has no clearance result.' };
    return { collision: typeof interval.collision === 'boolean' ? interval.collision : null, parts: interval.collision_parts || [], detail: interval.message, clearance: interval.clearance_mm };
  }
  const sorted = samples.filter((sample) => Number.isFinite(Number(sample.travel_mm ?? sample.travel))).sort((a, b) => (a.travel_mm ?? a.travel) - (b.travel_mm ?? b.travel));
  if (sorted.length) {
    const exact = sorted.find((sample) => Math.abs(Number(sample.travel_mm ?? sample.travel) - travel) < .0001);
    if (!exact) return { collision: null, parts: [] };
    const collision = exact.collision ?? exact.probe_collision ?? exact.interference ?? ((exact.collision_parts || []).length > 0);
    return { collision: Boolean(collision), parts: exact.collision_parts || exact.colliding_parts || [], detail: exact.clearance_message || exact.message, clearance: exact.probe_clearance_mm ?? exact.clearance_mm };
  }
  const limit = meta.safe_probe_travel_mm ?? meta.clearance_limit_mm ?? meta.clearance?.safe_travel_mm ?? manifest.clearance?.safe_travel_mm;
  if (limit !== undefined) return { collision: travel > Number(limit), parts: [], detail: null, limit: Number(limit) };
  return { collision: null, parts: [] };
}

function updateClearance() {
  const clearance = clearanceAt(state.travel);
  pose.clearance = clearance;
  const element = $('clearanceStatus'); element.classList.toggle('collision', clearance.collision === true); element.classList.toggle('warning', clearance.collision === null);
  if (state.explode > 0) {
    $('clearanceTitle').textContent = 'Exploded view'; $('clearanceDetail').textContent = 'Clearance indicator refers to the assembled position.';
    element.classList.remove('collision', 'warning');
  } else if (clearance.collision === true) {
    $('clearanceTitle').textContent = 'Probe assembly interference';
    $('clearanceDetail').textContent = clearance.detail || 'This raised position exceeds the probe clearance.';
  } else if (clearance.collision === false) {
    $('clearanceTitle').textContent = 'Modeled clearance checks passed';
    $('clearanceDetail').textContent = clearance.detail || (clearance.clearance !== undefined && clearance.clearance !== null ? `${Number(clearance.clearance).toFixed(1)} mm clearance at this position` : `At the modeled ${Number(model.meta?.workingDistance || model.meta?.working_distance_mm || 25)} mm working distance.`);
  } else {
    $('clearanceTitle').textContent = 'Probe clearance requires review';
    $('clearanceDetail').textContent = 'Clearance has not been verified at this position.';
  }
  const limit = model.meta?.safe_probe_travel_mm ?? model.meta?.clearance_limit_mm ?? model.meta?.clearance?.safe_travel_mm ?? manifest.clearance?.safe_travel_mm;
  $('travelProjection').textContent = limit !== undefined && Number(limit) < strokeMax ? `Probe clearance limit: ≈ ${Number(limit).toFixed(2)} mm vertical lift` : limit !== undefined ? `Nominal clearance checked across the ${strokeMax.toFixed(0)} mm stroke` : `${strokeMax.toFixed(0)} mm mechanical stroke · inspect probe clearance`;
  $('travelProjection').classList.toggle('clearance-range-note', clearance.collision === true);
  updateCollisionRows(); updateAppearance();
  window.currentPose = { ...pose };
}

function updateCollisionRows() {
  const collisions = pose.clearance?.parts || [];
  for (const part of state.parts) if (part.row) part.row.classList.toggle('collision-part', collisions.includes(part.name));
}

function updateAppearance() {
  for (const part of state.parts) {
    const selected = part === state.selected;
    const collision = state.explode === 0 && pose.clearance?.collision && pose.clearance.parts?.includes(part.name);
    part.material.color.copy(part.baseColor);
    if (collision) part.material.color.set(0xc47967);
    part.material.emissive.set(collision ? 0x6a1c0d : selected ? 0x144939 : 0x000000);
    part.material.emissiveIntensity = collision ? .3 : selected ? .19 : 0;
    part.material.opacity = state.ghost && !selected ? Math.min(part.baseOpacity, .22) : part.baseOpacity;
    part.material.transparent = part.material.opacity < 1; part.material.depthWrite = part.material.opacity > .5;
    part.edges.visible = state.edges || selected;
    part.edges.material.color.set(collision ? 0xad6149 : selected ? 0x244e3a : 0x526e5a);
    part.edges.material.opacity = selected ? .65 : .24;
  }
}

function setCamera(view, focusBounds = null) {
  if (!state.ready) return;
  if (view === 'motor-rear' && !controllerReference) view = 'iso';
  state.cameraView = view;
  setControllerReservation(state.controllerReservation);
  if (view === 'microscope') {
    setOpticalKeepout(true); setOpticalCamera();
    $('fitView').title = 'Fit projected optical view'; $('fitView').setAttribute('aria-label', 'Fit projected optical view');
    document.querySelectorAll('[data-view]').forEach((button) => { button.classList.toggle('active', button.dataset.view === view); button.setAttribute('aria-pressed', String(button.dataset.view === view)); });
    return;
  }
  camera.fov = 34; camera.updateProjectionMatrix(); controls.minDistance = 25;
  $('fitView').title = 'Fit assembly in view'; $('fitView').setAttribute('aria-label', 'Fit assembly in view');
  let box = focusBounds || bounds;
  if (view === 'motor-rear' && controllerReference) {
    box = new THREE.Box3().setFromObject(controllerReference.group);
    for (const part of state.parts.filter((part) => /NEMA17|microscope_reference|rear_clamp|frame_front_clamp/.test(part.name))) box.expandByObject(part.object);
  }
  if (!box || box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const aspectAllowance = Math.max(1, 1 / camera.aspect);
  baseDistance = Math.max(85, maxDim / (2 * Math.tan(deg(camera.fov / 2))) * 1.24 * aspectAllowance);
  const directions = { iso: [1.05, .52, 1.8], front: [0, 0, 1], side: [1, 0, 0], top: [0, 1, .001], 'motor-rear': [.65, .24, -1.8] };
  const direction = new THREE.Vector3(...(directions[view] || directions.iso)).normalize();
  camera.position.copy(center).addScaledVector(direction, baseDistance);
  setCameraUp([0, 1, 0]);
  controls.target.copy(center); controls.update();
  document.querySelectorAll('[data-view]').forEach((button) => { button.classList.toggle('active', button.dataset.view === view); button.setAttribute('aria-pressed', String(button.dataset.view === view)); });
}

function fitCurrentView() {
  if (!state.ready) return;
  if (state.cameraView === 'microscope') { setOpticalCamera(); return; }
  const visibleBounds = new THREE.Box3(); state.parts.filter((part) => part.object.visible).forEach((part) => visibleBounds.expandByObject(part.object));
  if (visibleBounds.isEmpty()) { toast('Show a component to fit the view.'); return; }
  const direction = camera.position.clone().sub(controls.target).normalize();
  const size = visibleBounds.getSize(new THREE.Vector3());
  const distance = Math.max(85, Math.max(size.x, size.y, size.z) / (2 * Math.tan(deg(camera.fov / 2))) * 1.24 * Math.max(1, 1 / camera.aspect));
  controls.target.copy(visibleBounds.getCenter(new THREE.Vector3())); camera.position.copy(controls.target).addScaledVector(direction, distance); controls.update();
}

function pick(event) {
  if (!state.ready) return null;
  const rect = canvas.getBoundingClientRect(); pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(meshObjects.filter((mesh) => mesh.parent.visible), false);
  // Transparent microscope reference remains selectable without obscuring the mechanism.
  const opaqueHit = hits.find((hit) => hit.object.userData.part.baseOpacity > .5);
  return (opaqueHit || hits[0])?.object.userData.part || null;
}

function drawAxis() {
  const axis = $('axisCanvas'), ctx = axis.getContext('2d');
  ctx.clearRect(0, 0, 150, 150);
  const axes = [ { v: new THREE.Vector3(1, 0, 0), color: '#a66f59', label: 'X' }, { v: new THREE.Vector3(0, 1, 0), color: '#78957a', label: 'Y' }, { v: new THREE.Vector3(0, 0, 1), color: '#6a91a2', label: 'Z' } ];
  const rotation = camera.quaternion.clone().invert();
  axes.forEach((item) => item.v.applyQuaternion(rotation)); axes.sort((a, b) => a.v.z - b.v.z);
  ctx.lineCap = 'round'; ctx.font = '600 16px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (const item of axes) {
    const x = 75 + item.v.x * 43, y = 75 - item.v.y * 43;
    ctx.strokeStyle = item.color; ctx.globalAlpha = item.v.z < -.15 ? .45 : .9; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.moveTo(75, 75); ctx.lineTo(x, y); ctx.stroke();
    ctx.fillStyle = '#f5f8f4'; ctx.beginPath(); ctx.arc(x, y, 12, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = item.color; ctx.fillText(item.label, x, y + 1);
  }
  ctx.globalAlpha = 1; ctx.fillStyle = '#91a393'; ctx.beginPath(); ctx.arc(75, 75, 3, 0, Math.PI * 2); ctx.fill();
}

function setPlaying(playing) {
  playing = Boolean(playing && state.ready);
  state.playing = playing; $('playMotion').setAttribute('aria-pressed', String(playing));
  $('playMotion').setAttribute('aria-label', playing ? 'Pause mechanism motion' : 'Play mechanism motion'); $('playMotion').title = playing ? 'Pause mechanism motion' : 'Play mechanism motion';
  $('playIcon').innerHTML = playing ? '<path d="M7 5h3v14H7zM14 5h3v14h-3z"/>' : '<path d="m9 5 11 7-11 7V5Z"/>';
}

function frame(time) {
  animationFrame = requestAnimationFrame(frame);
  const elapsed = Math.min((time - (state.lastTime || time)) / 1000, .05); state.lastTime = time;
  if (state.ready && state.playing) {
    let travel = state.travel + elapsed * 8 * state.direction;
    if (travel >= strokeMax) { travel = strokeMax; state.direction = -1; } else if (travel <= 0) { travel = 0; state.direction = 1; }
    updatePose(travel);
  }
  controls?.update();
  if (renderer && camera) { renderer.render(scene, camera); drawAxis(); }
}

function bindEvents() {
  $('versionSelect').addEventListener('change', (event) => loadVersion(event.target.value, { history: true }));
  $('retryVersion').addEventListener('click', () => loadVersion(retryVersionId || $('versionSelect').value, { force: true }));
  window.addEventListener('popstate', () => {
    const requested = new URL(location.href).searchParams.get('version'), available = catalog.versions.find((version) => version.id === requested && version.available === true);
    const id = available?.id || catalog.defaultVersion;
    if (requested && !available) { const url = new URL(location.href); url.searchParams.set('version', id); history.replaceState({ version: id }, '', url); toast('That version is not available. Opening the current release.'); }
    loadVersion(id);
  });
  $('partSearch').addEventListener('input', buildPartList);
  $('showAll').addEventListener('click', () => { state.hidden.clear(); state.isolate = false; updateVisibility(); });
  $('isolate').addEventListener('click', () => { if (state.selected) { state.isolate = !state.isolate; updateVisibility(); if (state.isolate) setCamera('iso', new THREE.Box3().setFromObject(state.selected.object)); else setCamera('iso'); } });
  $('focusPart').addEventListener('click', () => { if (state.selected) { state.hidden.delete(state.selected.name); updateVisibility(); setCamera('iso', new THREE.Box3().setFromObject(state.selected.object)); } });
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setCamera(button.dataset.view)));
  $('fitView').addEventListener('click', fitCurrentView);
  $('edgesToggle').addEventListener('click', () => { state.edges = !state.edges; $('edgesToggle').setAttribute('aria-pressed', String(state.edges)); updateAppearance(); });
  $('ghostToggle').addEventListener('click', () => { state.ghost = !state.ghost; $('ghostToggle').setAttribute('aria-pressed', String(state.ghost)); updateAppearance(); });
  $('opticalKeepout').addEventListener('change', (event) => setOpticalKeepout(event.target.checked));
  $('controllerSpace').addEventListener('change', (event) => setControllerReservation(event.target.checked));
  $('helpToggle').addEventListener('click', () => { $('navigationHelp').hidden = !$('navigationHelp').hidden; $('helpToggle').setAttribute('aria-expanded', String(!$('navigationHelp').hidden)); });
  $('notesToggle').addEventListener('click', () => { $('designNotes').hidden = !$('designNotes').hidden; $('notesToggle').setAttribute('aria-expanded', String(!$('designNotes').hidden)); });
  $('playMotion').addEventListener('click', () => setPlaying(!state.playing));
  $('travelSlider').addEventListener('input', (event) => { setPlaying(false); updatePose(event.target.value); });
  $('lowerProbe').addEventListener('click', () => { setPlaying(false); updatePose(0); });
  $('raiseProbe').addEventListener('click', () => { setPlaying(false); updatePose(strokeMax); });
  $('explodeSlider').addEventListener('input', (event) => { state.explode = Number(event.target.value) / 100; $('explodeValue').textContent = `${event.target.value}%`; setPlaying(false); updatePose(state.travel); });
  canvas.addEventListener('pointerdown', (event) => { state.pointer = { x: event.clientX, y: event.clientY, button: event.button }; $('hoverLabel').hidden = true; });
  canvas.addEventListener('pointerup', (event) => { if (state.pointer?.button === 0 && Math.hypot(event.clientX - state.pointer.x, event.clientY - state.pointer.y) < 5) { const part = pick(event); if (part) selectPart(part); } state.pointer = null; });
  canvas.addEventListener('pointermove', (event) => {
    if (state.pointer || event.pointerType === 'touch') return;
    const part = pick(event); state.hover = part; canvas.style.cursor = part ? 'pointer' : 'grab';
    if (!part) { $('hoverLabel').hidden = true; return; }
    const rect = viewport.getBoundingClientRect(); $('hoverLabel').textContent = part.meta.title;
    $('hoverLabel').style.left = `${clamp(event.clientX - rect.left + 12, 12, rect.width - 200)}px`; $('hoverLabel').style.top = `${clamp(event.clientY - rect.top + 13, 12, rect.height - 36)}px`; $('hoverLabel').hidden = false;
  });
  canvas.addEventListener('pointerleave', () => { $('hoverLabel').hidden = true; state.pointer = null; });
  canvas.addEventListener('dblclick', (event) => { const part = pick(event); if (part) { selectPart(part); setCamera('iso', new THREE.Box3().setFromObject(part.object)); } });
  document.addEventListener('keydown', (event) => {
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || document.activeElement.isContentEditable) return;
    if (event.key === '/') { event.preventDefault(); $('partSearch').focus(); }
    if (event.key === 'Escape') { if (state.isolate) { state.isolate = false; updateVisibility(); } $('navigationHelp').hidden = true; }
    if (event.key.toLowerCase() === 'f') { event.preventDefault(); fitCurrentView(); }
    if (document.activeElement !== viewport && document.activeElement !== canvas) return;
    if (event.code === 'Space') { event.preventDefault(); setPlaying(!state.playing); }
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
      event.preventDefault(); const offset = camera.position.clone().sub(controls.target); const spherical = new THREE.Spherical().setFromVector3(offset);
      if (event.key === 'ArrowLeft') spherical.theta -= .12; if (event.key === 'ArrowRight') spherical.theta += .12;
      if (event.key === 'ArrowUp') spherical.phi = clamp(spherical.phi - .1, .05, Math.PI - .05); if (event.key === 'ArrowDown') spherical.phi = clamp(spherical.phi + .1, .05, Math.PI - .05);
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical)); controls.update();
    }
    if (['+', '=', '-', '_'].includes(event.key)) { event.preventDefault(); camera.position.sub(controls.target).multiplyScalar(event.key === '-' || event.key === '_' ? 1.12 : .89).add(controls.target); controls.update(); }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) setPlaying(false); });
}

function loadingStatus(version, loading) {
  const status = $('versionStatus'); status.hidden = !loading; status.textContent = loading ? `Loading ${version.label}…` : '';
  $('retryVersion').hidden = true; retryVersionId = null;
  if (!activeBundle) {
    $('loadState').hidden = false; $('loadState').querySelector('.spinner').hidden = false;
    $('loadState').querySelector('strong').textContent = 'Preparing the assembly'; $('loadState').querySelector('span').textContent = `Loading ${version.label}…`;
  }
}

async function loadVersion(id, options = {}) {
  const version = catalog?.versions.find((item) => item.id === id && item.available === true);
  if (!version) {
    if (activeVersion) $('versionSelect').value = activeVersion.id;
    toast('That version is not available yet.'); return false;
  }
  if (activeVersion?.id === id && !options.force && !loadController) return true;
  loadController?.abort(); const controller = new AbortController(), token = ++loadToken; loadController = controller;
  setPlaying(false); loadingStatus(version, true);
  let candidate;
  try {
    const manifestUrl = versionURL(version.manifest || './assets/manifest.json', version);
    if (!manifestUrl) throw new Error('The version manifest path is invalid.');
    const response = await fetch(manifestUrl, { signal: controller.signal });
    if (!response.ok) throw new Error('The version manifest could not be loaded.');
    const candidateManifest = await response.json();
    if (token !== loadToken) return false;
    const modelUrl = versionURL(candidateManifest.model || './assets/model.json', version);
    if (!modelUrl) throw new Error('The model path is invalid.');
    const geometry = await fetch(modelUrl, { signal: controller.signal });
    if (!geometry.ok) throw new Error('The model geometry could not be loaded.');
    const candidateModel = await geometry.json();
    if (token !== loadToken) return false;
    candidate = buildBundle(candidateModel, candidateManifest, version);
    if (token !== loadToken) { disposeBundle(candidate); return false; }
    installBundle(candidate, captureView()); candidate = null;
    if (options.history) { const url = new URL(location.href); url.searchParams.set('version', version.id); history.pushState({ version: version.id }, '', url); }
    else if (new URL(location.href).searchParams.get('version') !== version.id) { const url = new URL(location.href); url.searchParams.set('version', version.id); history.replaceState({ version: version.id }, '', url); }
    loadingStatus(version, false); return true;
  } catch (error) {
    disposeBundle(candidate);
    if (token !== loadToken || error.name === 'AbortError') return false;
    console.warn('Version load failed:', error.message);
    $('versionStatus').hidden = false; $('versionStatus').textContent = `Could not load ${version.label}.`;
    $('retryVersion').hidden = false; retryVersionId = version.id;
    if (activeVersion) { $('versionSelect').value = activeVersion.id; toast(`${version.label} could not be loaded. ${activeVersion.label} remains open.`); }
    else { $('loadState').querySelector('.spinner').hidden = true; $('loadState').querySelector('strong').textContent = 'The model could not be loaded'; $('loadState').querySelector('span').textContent = 'Use Retry above to try again.'; }
    return false;
  } finally { if (token === loadToken) loadController = null; }
}

async function start() {
  try {
    const response = await fetch('./versions.json');
    if (!response.ok) throw new Error('The version catalog could not be loaded.');
    catalog = await response.json();
    if (!Array.isArray(catalog.versions) || !catalog.versions.some((version) => version.available === true)) throw new Error('There are no available versions.');
    const ids = new Set();
    for (const version of catalog.versions) {
      if (!/^[a-zA-Z0-9_-]+$/.test(version.id) || ids.has(version.id)) throw new Error('Version IDs are invalid.'); ids.add(version.id);
      const base = new URL(version.base, document.baseURI);
      if (base.origin !== location.origin || !base.pathname.endsWith('/') || !['http:', 'https:'].includes(base.protocol) || base.username || base.password) throw new Error('Version paths are invalid.');
      const option = document.createElement('option'); option.value = version.id; option.textContent = version.label + (version.available === true ? '' : ' — preparing'); option.disabled = version.available !== true; $('versionSelect').append(option);
    }
    $('repositoryLink').href = catalog.repository || 'https://github.com/tscircuit/probe-stage01';
    initScene(); bindEvents(); animationFrame = requestAnimationFrame(frame);
    window.inspector = { state, get model() { return model; }, get manifest() { return manifest; }, get versionId() { return activeVersion?.id; }, get activeVersion() { return activeVersion; }, get controllerReference() { return controllerReference; }, loadVersion, setTravel: (travel) => { setPlaying(false); updatePose(travel); }, setCamera, setControllerReservation, fitCurrentView, selectPart: (name) => selectPart(state.parts.find((part) => part.name === name)), renderer, scene, camera, controls, resourceStats: () => ({ versionRoots: scene.children.filter((child) => child.name === 'Version model').length, parts: state.parts.length, pickMeshes: meshObjects.length, controllerAnnotations: scene.getObjectByName('Version model') ? (() => { let count = 0; scene.getObjectByName('Version model').traverse((object) => { if (object.name === 'Controller space annotation') count++; }); return count; })() : 0, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures }) };
    const requested = new URL(location.href).searchParams.get('version'), initial = catalog.versions.find((version) => version.id === requested && version.available === true) || catalog.versions.find((version) => version.id === catalog.defaultVersion && version.available === true) || catalog.versions.find((version) => version.available === true);
    if (requested && requested !== initial.id) toast('That version is not available. Opening the current release.');
    $('versionSelect').value = initial.id; await loadVersion(initial.id);
  } catch (error) {
    console.error(error); $('loadState').querySelector('.spinner').hidden = true; $('loadState').querySelector('strong').textContent = 'The model could not be loaded'; $('loadState').querySelector('span').textContent = 'Refresh the page to try again.';
  }
}

start();
