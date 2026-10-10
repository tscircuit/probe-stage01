import * as THREE from 'three';
import { OrbitControls } from './assets/vendor/OrbitControls.js';

const $ = (id) => document.getElementById(id);
const viewport = $('viewport');
const canvas = $('modelCanvas');
const state = { parts: [], selected: null, hidden: new Set(), isolate: false, edges: false, ghost: false, playing: false, travel: 0, explode: 0, direction: 1, ready: false, lastTime: 0, pointer: null, hover: null, cameraView: 'iso', opticalKeepout: false };
let model, manifest, scene, renderer, camera, controls, mechanism, contextGroup, opticalGroup, opticalReference, bounds, baseDistance = 300;
let kinematics = {}, meshObjects = [], selectionEdge, pose = {};
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const eyeIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
const hiddenIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 3 18 18M9.5 5.3A12 12 0 0 1 12 5c6.5 0 10 7 10 7a20 20 0 0 1-3 3.8M6 6A21 21 0 0 0 2 12s3.5 7 10 7c1.7 0 3.3-.5 4.6-1.2"/></svg>';
const humanize = (name) => name.replace(/_/g, ' ').replace(/\bzz\b/ig, 'ZZ').replace(/\bnema17\b/ig, 'NEMA17').replace(/\b625zz\b/ig, '625ZZ').replace(/\bm5\b/ig, 'M5').replace(/\bm3\b/ig, 'M3').replace(/^\w/, (s) => s.toUpperCase());
const colorString = (color) => Array.isArray(color) ? new THREE.Color(color[0], color[1], color[2]).getStyle() : (color || '#7c9b8e');
const clamp = THREE.MathUtils.clamp;
const deg = THREE.MathUtils.degToRad;
const safePath = (path) => typeof path === 'string' && !/^(?:javascript|data):/i.test(path) ? path : null;

function toast(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(toast.timeout);
  toast.timeout = setTimeout(() => $('toast').hidden = true, 2600);
}

function linkDownload(id, path) {
  const element = $(id);
  const safe = safePath(path);
  if (safe) { element.href = safe; element.classList.remove('disabled'); element.removeAttribute('aria-disabled'); element.hidden = false; }
  else { element.removeAttribute('href'); element.classList.add('disabled'); element.setAttribute('aria-disabled', 'true'); }
}

function metadataFor(part) {
  const entries = manifest?.parts || {};
  const entry = Array.isArray(entries) ? entries.find((item) => item.name === part.name || item.id === part.name) : entries[part.name];
  const category = entry?.category || (part.motion === 'fixed_world' || part.reference || /reference/i.test(part.name) ? 'References' : model?.meta?.printable?.includes(part.name) ? 'Fabricated parts' : 'Hardware');
  return { ...entry, name: part.name, title: entry?.title || part.title || humanize(part.name), category, description: entry?.description || part.description, dimensions: entry?.dimensions || part.dimensions, quantity: entry?.quantity || part.quantity, material: typeof entry?.material === 'string' ? entry.material : null, step: entry?.step || entry?.stepUrl, xt: entry?.xt || entry?.xtUrl };
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
}

function togglePart(part) {
  if (state.isolate) { state.isolate = false; state.hidden = new Set(state.parts.filter((p) => !p.object.visible).map((p) => p.name)); }
  if (state.hidden.has(part.name)) state.hidden.delete(part.name); else state.hidden.add(part.name);
  updateVisibility();
}

function selectPart(part) {
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
  linkDownload('xtDownload', part.meta.xt || part.meta.xtUrl);
  $('xtDownload').querySelector('.unavailable-tag').hidden = Boolean(part.meta.xt || part.meta.xtUrl);
  $('exportNote').textContent = part.meta.xt || part.meta.xtUrl ? 'Solid CAD files for this component.' : 'x_t export is unavailable. Import STEP into a Parasolid CAD tool to convert.';
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
  controls.addEventListener('start', () => document.querySelectorAll('[data-view]').forEach((button) => { button.classList.remove('active'); button.setAttribute('aria-pressed', 'false'); }));
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb1c0ac, 2.0));
  const key = new THREE.DirectionalLight(0xfffdf3, 3.1); key.position.set(-200, 340, 330); scene.add(key);
  const rim = new THREE.DirectionalLight(0xc2dce8, 1.4); rim.position.set(230, 80, -250); scene.add(rim);
  const fill = new THREE.DirectionalLight(0xf2fff8, 0.75); fill.position.set(160, -100, 260); scene.add(fill);
  mechanism = new THREE.Group(); contextGroup = new THREE.Group(); scene.add(mechanism, contextGroup);
  resize(); new ResizeObserver(resize).observe(viewport);
}

function resize() {
  if (!renderer) return;
  const width = viewport.clientWidth, height = viewport.clientHeight;
  if (!width || !height) return;
  renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
  if (state.ready && state.cameraView === 'microscope') setOpticalCamera();
}

function buildModel() {
  const meta = model.meta || {};
  kinematics = { crank_radius: 25, rod_length: 100, phi_min: -Math.asin(.8), phi_max: Math.asin(.8), pinion_ratio: 6, pinion_center: [-50, 0, 0], ...meta.kinematics };
  if (meta.crank_radius) kinematics.crank_radius = meta.crank_radius;
  if (meta.crankRadius) kinematics.crank_radius = meta.crankRadius;
  if (meta.rod_length) kinematics.rod_length = meta.rod_length;
  if (meta.rodLength) kinematics.rod_length = meta.rodLength;
  if (meta.phi_min_rad !== undefined) kinematics.phi_min = meta.phi_min_rad;
  if (meta.phi_max_rad !== undefined) kinematics.phi_max = meta.phi_max_rad;
  if (meta.pinion_ratio) kinematics.pinion_ratio = meta.pinion_ratio;
  if (meta.ratio) kinematics.pinion_ratio = meta.ratio;
  if (meta.pinion_center) kinematics.pinion_center = meta.pinion_center;
  if (meta.pinionCenter) kinematics.pinion_center = meta.pinionCenter;
  if (meta.limitDegrees && meta.kinematics?.phi_min === undefined) { kinematics.phi_min = -deg(meta.limitDegrees); kinematics.phi_max = deg(meta.limitDegrees); }
  if (meta.kinematics?.angle_units === 'degrees' || Math.abs(kinematics.phi_min) > Math.PI || Math.abs(kinematics.phi_max) > Math.PI) { kinematics.phi_min = deg(kinematics.phi_min); kinematics.phi_max = deg(kinematics.phi_max); }
  const transform = meta.world_transform || meta.kinematics?.world_transform || meta.localToWorld || {};
  const translation = transform.translation || meta.wheel_origin || [meta.wheel_origin_x || 0, meta.wheel_origin_y || 0, meta.wheel_origin_z || 0];
  mechanism.position.fromArray(translation);
  mechanism.rotation.z = deg(transform.rotation_deg ?? transform.rotationZDegrees ?? meta.world_rotation_deg ?? 0);
  for (const raw of model.parts) {
    if (!raw.vertices?.length || !raw.triangles?.length) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(raw.vertices.flat(), 3));
    geometry.setIndex(raw.triangles.flat());
    geometry.computeVertexNormals(); geometry.computeBoundingBox();
    const opacity = raw.opacity ?? (Array.isArray(raw.color) ? raw.color[3] : null) ?? 1;
    const displayColor = raw.name === 'probe_reference' ? '#5e7682' : raw.name === 'motor_pinion' ? '#79909b' : raw.color;
    const color = Array.isArray(displayColor) ? new THREE.Color(displayColor[0], displayColor[1], displayColor[2]) : new THREE.Color(displayColor || '#809d8c');
    const metal = /bearing|bolt|nut|washer|shaft|rail|probe/i.test(raw.name);
    const material = new THREE.MeshStandardMaterial({ color, roughness: metal ? .37 : .61, metalness: metal ? .48 : .06, transparent: opacity < 1, opacity, depthWrite: opacity > .5, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geometry, material);
    const group = new THREE.Group(); group.add(mesh);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28), new THREE.LineBasicMaterial({ color: 0x42614f, transparent: true, opacity: .28, depthWrite: false }));
    group.add(edges); edges.visible = false; edges.renderOrder = 1;
    const part = { ...raw, color: displayColor, object: group, mesh, edges, material, baseOpacity: opacity, baseColor: color.clone(), visible: true };
    part.meta = metadataFor(part); mesh.userData.part = part;
    (raw.motion === 'fixed_world' ? contextGroup : mechanism).add(group);
    state.parts.push(part); meshObjects.push(mesh);
    geometry.computeBoundingSphere();
  }
  const gridY = meta.specimen_plate_y ?? meta.specimen_y ?? -Number(meta.workingDistance || meta.working_distance_mm || 25);
  const grid = new THREE.GridHelper(360, 36, 0xc6d5c6, 0xd9e3d7);
  grid.position.set(meta.optical_center_x || 0, gridY - 1.2, 0); grid.material.transparent = true; grid.material.opacity = .34; grid.material.depthWrite = false;
  contextGroup.add(grid);
  buildOpticalReference(meta);
  selectionEdge = new THREE.Group(); scene.add(selectionEdge);
  const downloads = manifest.downloads || {};
  linkDownload('assemblyDownload', downloads.assemblyStep || downloads.assembly_step || manifest.assemblyStep);
  linkDownload('sourceDownload', downloads.source || manifest.source);
  linkDownload('bundleDownload', downloads.bundle || manifest.bundle);
  if (manifest.notes?.fit) $('fitNotes').textContent = manifest.notes.fit;
  if (manifest.notes?.validation) $('validationNotes').textContent = manifest.notes.validation;
  if (manifest.notes?.exports) $('cadNotes').textContent = manifest.notes.exports;
  const samples = meta.clearance_samples || meta.pose_samples || meta.samples || [];
  kinematics.samples = samples;
  const limit = meta.safe_probe_travel_mm ?? meta.clearance_limit_mm ?? meta.clearance?.safe_travel_mm ?? manifest.clearance?.safe_travel_mm;
  if (limit !== undefined && Number.isFinite(Number(limit)) && Number(limit) > 0 && Number(limit) < 40) {
    const slider = $('travelSlider');
    const wrapper = document.createElement('div'); wrapper.className = 'travel-range-wrap';
    slider.replaceWith(wrapper); wrapper.append(slider);
    const marker = document.createElement('span'); marker.className = 'clearance-limit'; marker.style.left = `${clamp(Number(limit) / 40 * 100, 0, 100)}%`; marker.title = `Probe clearance limit: ${Number(limit).toFixed(1)} mm`; wrapper.append(marker);
  }
  updatePose(0); updateAppearance(); buildPartList();
  bounds = new THREE.Box3().setFromObject(mechanism).union(new THREE.Box3().setFromObject(contextGroup));
  // The inspection grid is intentionally excluded from camera framing.
  bounds = new THREE.Box3(); state.parts.forEach((part) => bounds.expandByObject(part.object));
  setCamera('iso');
  state.ready = true; $('loadState').hidden = true;
  const initial = state.parts.find((part) => /crank.*wheel|crank_gear|sector_gear|sector_crank/i.test(part.name)) || state.parts.find((part) => part.meta.category === 'Fabricated parts');
  if (initial) selectPart(initial);
  window.modelReady = true;
}

function buildOpticalReference(meta) {
  const optical = meta.optical_keepout || {};
  const workingDistance = Number(meta.workingDistance || meta.working_distance_mm || 25);
  $('workingDistanceValue').textContent = workingDistance.toFixed(0);
  opticalReference = { radius: Number(optical.radius_mm || 22), top: Number(optical.barrel_end_y ?? 0), bottom: Number(optical.specimen_y ?? -workingDistance), x: Number(optical.center_x || 0), z: Number(optical.center_z || 0) };
  const { radius, top, bottom, x, z } = opticalReference;
  const height = Math.abs(top - bottom);
  opticalGroup = new THREE.Group(); opticalGroup.name = 'Optical clearance annotation';
  const volume = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, 64, 1), new THREE.MeshBasicMaterial({ color: 0x4ba5b2, transparent: true, opacity: .055, side: THREE.DoubleSide, depthWrite: false }));
  volume.position.set(x, (top + bottom) / 2, z); volume.renderOrder = 2; opticalGroup.add(volume);
  for (const y of [top, bottom]) {
    const points = Array.from({ length: 97 }, (_, index) => { const angle = index / 96 * Math.PI * 2; return new THREE.Vector3(x + Math.cos(angle) * radius, y, z + Math.sin(angle) * radius); });
    const ring = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineDashedMaterial({ color: 0x418d9e, transparent: true, opacity: .75, dashSize: 1.4, gapSize: .8, depthWrite: false }));
    ring.computeLineDistances(); ring.renderOrder = 3; opticalGroup.add(ring);
  }
  for (const angle of [0, Math.PI / 2, Math.PI, Math.PI * 1.5]) {
    const px = x + Math.cos(angle) * radius, pz = z + Math.sin(angle) * radius;
    const edge = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(px, top, pz), new THREE.Vector3(px, bottom, pz)]), new THREE.LineDashedMaterial({ color: 0x70aab4, transparent: true, opacity: .3, dashSize: 2, gapSize: 2, depthWrite: false }));
    edge.computeLineDistances(); opticalGroup.add(edge);
  }
  opticalGroup.visible = false; scene.add(opticalGroup);
  $('opticalCaption').querySelector('strong').textContent = `Ø${(radius * 2).toFixed(0)} mm barrel projection`;
  $('clearanceDetail').textContent = `${workingDistance} mm microscope working distance`;
}

function setOpticalKeepout(visible) {
  state.opticalKeepout = Boolean(visible);
  opticalGroup.visible = state.opticalKeepout;
  $('opticalKeepout').checked = state.opticalKeepout;
  $('opticalCaption').hidden = !state.opticalKeepout;
  viewport.classList.toggle('show-optical', state.opticalKeepout);
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
  state.travel = clamp(Number(travel), 0, 40);
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
  pose = { phi, cx, cy, sy, travel: state.travel };
  $('travelSlider').value = state.travel;
  $('travelSlider').style.setProperty('--progress', `${state.travel / 40 * 100}%`);
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
    const interval = intervals.find((item) => travel >= Number(item.min_mm) && (travel < Number(item.max_mm) || (Number(item.max_mm) === 40 && travel <= 40)));
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
  $('travelProjection').textContent = limit !== undefined && Number(limit) < 40 ? `Probe clearance limit: ≈ ${Number(limit).toFixed(2)} mm vertical lift` : limit !== undefined ? 'Nominal clearance checked across the 40 mm stroke' : '40 mm mechanical stroke · inspect probe clearance';
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
  state.cameraView = view;
  if (view === 'microscope') {
    setOpticalKeepout(true); setOpticalCamera();
    $('fitView').title = 'Fit projected optical view'; $('fitView').setAttribute('aria-label', 'Fit projected optical view');
    document.querySelectorAll('[data-view]').forEach((button) => { button.classList.toggle('active', button.dataset.view === view); button.setAttribute('aria-pressed', String(button.dataset.view === view)); });
    return;
  }
  camera.fov = 34; camera.updateProjectionMatrix(); controls.minDistance = 25;
  $('fitView').title = 'Fit assembly in view'; $('fitView').setAttribute('aria-label', 'Fit assembly in view');
  const box = focusBounds || bounds;
  if (!box || box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const aspectAllowance = Math.max(1, 1 / camera.aspect);
  baseDistance = Math.max(85, maxDim / (2 * Math.tan(deg(camera.fov / 2))) * 1.24 * aspectAllowance);
  const directions = { iso: [1.05, .52, 1.8], front: [0, 0, 1], side: [1, 0, 0], top: [0, 1, .001] };
  const direction = new THREE.Vector3(...(directions[view] || directions.iso)).normalize();
  camera.position.copy(center).addScaledVector(direction, baseDistance);
  setCameraUp([0, 1, 0]);
  controls.target.copy(center); controls.update();
  document.querySelectorAll('[data-view]').forEach((button) => { button.classList.toggle('active', button.dataset.view === view); button.setAttribute('aria-pressed', String(button.dataset.view === view)); });
}

function fitCurrentView() {
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
  state.playing = playing; $('playMotion').setAttribute('aria-pressed', String(playing));
  $('playMotion').setAttribute('aria-label', playing ? 'Pause mechanism motion' : 'Play mechanism motion'); $('playMotion').title = playing ? 'Pause mechanism motion' : 'Play mechanism motion';
  $('playIcon').innerHTML = playing ? '<path d="M7 5h3v14H7zM14 5h3v14h-3z"/>' : '<path d="m9 5 11 7-11 7V5Z"/>';
}

function frame(time) {
  requestAnimationFrame(frame);
  const elapsed = Math.min((time - (state.lastTime || time)) / 1000, .05); state.lastTime = time;
  if (state.ready && state.playing) {
    let travel = state.travel + elapsed * 8 * state.direction;
    if (travel >= 40) { travel = 40; state.direction = -1; } else if (travel <= 0) { travel = 0; state.direction = 1; }
    updatePose(travel);
  }
  controls?.update();
  if (renderer && camera) { renderer.render(scene, camera); drawAxis(); }
}

function bindEvents() {
  $('partSearch').addEventListener('input', buildPartList);
  $('showAll').addEventListener('click', () => { state.hidden.clear(); state.isolate = false; updateVisibility(); });
  $('isolate').addEventListener('click', () => { if (state.selected) { state.isolate = !state.isolate; updateVisibility(); if (state.isolate) setCamera('iso', new THREE.Box3().setFromObject(state.selected.object)); else setCamera('iso'); } });
  $('focusPart').addEventListener('click', () => { if (state.selected) { state.hidden.delete(state.selected.name); updateVisibility(); setCamera('iso', new THREE.Box3().setFromObject(state.selected.object)); } });
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setCamera(button.dataset.view)));
  $('fitView').addEventListener('click', fitCurrentView);
  $('edgesToggle').addEventListener('click', () => { state.edges = !state.edges; $('edgesToggle').setAttribute('aria-pressed', String(state.edges)); updateAppearance(); });
  $('ghostToggle').addEventListener('click', () => { state.ghost = !state.ghost; $('ghostToggle').setAttribute('aria-pressed', String(state.ghost)); updateAppearance(); });
  $('opticalKeepout').addEventListener('change', (event) => setOpticalKeepout(event.target.checked));
  $('helpToggle').addEventListener('click', () => { $('navigationHelp').hidden = !$('navigationHelp').hidden; $('helpToggle').setAttribute('aria-expanded', String(!$('navigationHelp').hidden)); });
  $('notesToggle').addEventListener('click', () => { $('designNotes').hidden = !$('designNotes').hidden; $('notesToggle').setAttribute('aria-expanded', String(!$('designNotes').hidden)); });
  $('playMotion').addEventListener('click', () => setPlaying(!state.playing));
  $('travelSlider').addEventListener('input', (event) => { setPlaying(false); updatePose(event.target.value); });
  $('lowerProbe').addEventListener('click', () => { setPlaying(false); updatePose(0); });
  $('raiseProbe').addEventListener('click', () => { setPlaying(false); updatePose(40); });
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
    if (/INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
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

async function start() {
  try {
    const response = await fetch('./assets/manifest.json');
    if (!response.ok) throw new Error('The assembly manifest could not be loaded.');
    manifest = await response.json();
    const geometry = await fetch(manifest.model || './assets/model.json');
    if (!geometry.ok) throw new Error('The model geometry could not be loaded.');
    model = await geometry.json();
    if (!Array.isArray(model.parts) || !model.parts.length) throw new Error('The assembly contains no display geometry.');
    initScene(); buildModel(); bindEvents(); requestAnimationFrame(frame);
    window.inspector = { state, model, manifest, setTravel: (travel) => { setPlaying(false); updatePose(travel); }, setCamera, fitCurrentView, selectPart: (name) => selectPart(state.parts.find((part) => part.name === name)), renderer, scene, camera, controls };
  } catch (error) {
    console.error(error);
    $('loadState').querySelector('.spinner').hidden = true;
    $('loadState').querySelector('strong').textContent = 'The model could not be loaded';
    $('loadState').querySelector('span').textContent = 'Refresh the page to try again.';
  }
}

start();
