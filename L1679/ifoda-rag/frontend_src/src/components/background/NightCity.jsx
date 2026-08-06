import { Canvas, useFrame, useThree } from '@react-three/fiber'
import {
  EffectComposer,
  Bloom,
  ChromaticAberration,
  Vignette,
} from '@react-three/postprocessing'
import { Html } from '@react-three/drei'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import CityModel from './CityModel'
import DetailedBuildings from './Buildings'

// ─────────────────────────────────────────────────────────────────────
// Cyberpunk 2077 / Night City — atmospheric background
//
// The pre-built cyberpunk city from /models/city.glb is the hero of this
// scene. We compose:
//   • Deep purple volumetric fog (only acts on the far horizon)
//   • Soft horizon glow shader sky
//   • Layered UnrealBloom on emissive neon (windows, signs)
//   • Slow panoramic camera drift (no zoom, no close-up)
//   • Per-material neon flicker (NeonFlicker) for "alive" signs
//   • Animated rain + flying cars foreground
//
// The UI panel renders in normal DOM at higher z-index and sits on top.
// ─────────────────────────────────────────────────────────────────────

const NEON_LIST = ['#00f0ff', '#ff2bd6', '#fcee0a', '#00ff88', '#ff7a00', '#ff2e4c']

// Source-model bbox center in local units. The exported GLB has its
// visual centre offset, so we shift the placement to compensate.
const CITY_SOURCE_CENTER = [3, 3.46, 0]

// ─────────────────────────────────────────────────────────────────────
// SkyDome — gradient horizon (deep purple → magenta → dark top)
// ─────────────────────────────────────────────────────────────────────
function SkyDome() {
  const material = useMemo(() => {
    const uniforms = {
      topColor: { value: new THREE.Color('#050520') },
      midColor: { value: new THREE.Color('#2d0840') },
      horizonColor: { value: new THREE.Color('#6a1040') },
      bottomColor: { value: new THREE.Color('#0d0218') },
    }
    return new THREE.ShaderMaterial({
      uniforms,
      side: THREE.BackSide,
      depthWrite: false,
      vertexShader: `
        varying vec3 vWorldPosition;
        void main() {
          vec4 worldPosition = modelMatrix * vec4(position, 1.0);
          vWorldPosition = worldPosition.xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 topColor;
        uniform vec3 midColor;
        uniform vec3 horizonColor;
        uniform vec3 bottomColor;
        varying vec3 vWorldPosition;
        void main() {
          float h = normalize(vWorldPosition).y;
          vec3 col;
          if (h > 0.0) {
            float t = pow(clamp(h, 0.0, 1.0), 0.55);
            col = mix(midColor, topColor, t);
          } else {
            col = mix(bottomColor, midColor, clamp(-h * 2.0, 0.0, 1.0));
          }
          float band = exp(-pow(h * 5.0, 2.0)) * 0.85;
          col = mix(col, horizonColor, band * 0.7);
          gl_FragColor = vec4(col, 1.0);
        }
      `,
    })
  }, [])

  return (
    <mesh material={material} renderOrder={-1}>
      <sphereGeometry args={[400, 32, 16]} />
    </mesh>
  )
}

// ─────────────────────────────────────────────────────────────────────
// Rain — animated points (wider volume to cover the city scale)
// ─────────────────────────────────────────────────────────────────────
// (NeonSigns is defined above; this placeholder keeps the rain section
// right under the file-order it lived in before)

function FogMist() {
  return (
    <group>
      {Array.from({ length: 12 }).map((_, i) => (
        <mesh
          key={i}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, 0 - i * 2.2, -40 - i * 20]}
        >
          <planeGeometry args={[280, 28]} />
          <meshBasicMaterial
            color={i % 2 === 0 ? '#1a0840' : '#0d0530'}
            transparent
            opacity={0.22 - i * 0.012}
            depthWrite={false}
          />
        </mesh>
      ))}
      {/* Street-level ground fog — thicker, yellow-tinged like neon reflections */}
      {Array.from({ length: 4 }).map((_, i) => (
        <mesh
          key={`street-${i}`}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, -1.5 - i * 0.6, -40 - i * 10]}
        >
          <planeGeometry args={[200, 15]} />
          <meshBasicMaterial
            color={i % 2 === 0 ? '#2a1040' : '#3a1040'}
            transparent
            opacity={0.28 - i * 0.04}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  )
}

// ─────────────────────────────────────────────────────────────────────
// Camera — slow panoramic arc, stays well outside the city
// ─────────────────────────────────────────────────────────────────────
function CameraDolly() {
  const { camera } = useThree()
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    // Pulled further back — panoramic skyline, height low
    camera.position.x = 2 + Math.sin(t * 0.04) * 2.5
    camera.position.y = 7 + Math.sin(t * 0.1) * 0.3
    camera.position.z = 55 + Math.cos(t * 0.04) * 1.5
    camera.lookAt(0, 5, -70)
  })
  return null
}

// ─────────────────────────────────────────────────────────────────────
// NeonFlicker — drives subtle pulsing on saturated neon materials.
// Walks the scene once on mount, then modulates emissive/color per frame
// with deterministic noise + rare flicker dips.
// ─────────────────────────────────────────────────────────────────────
function NeonFlicker({ root }) {
  const targets = useRef([])
  const baseData = useRef([])

  useEffect(() => {
    if (!root) return
    const found = []
    const base = []
    root.traverse((obj) => {
      if (!obj.isMesh || !obj.material) return
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
      mats.forEach((m) => {
        if (!m) return
        // Pick the "colour channel" we want to pulse — emissive if present
        // (won't override toneMapped false), otherwise base color.
        const target =
          m.emissive && m.emissive.isColor
            ? m.emissive
            : m.color && m.color.isColor
            ? m.color
            : null
        if (!target) return
        const hsl = { h: 0, s: 0, l: 0 }
        target.getHSL(hsl)
        // Only modulate saturated neon, not dark building bodies
        if (hsl.s < 0.55 || hsl.l < 0.45 || hsl.l > 0.9) return
        found.push(target)
        base.push({
          r: target.r,
          g: target.g,
          b: target.b,
          phase: Math.random() * Math.PI * 2,
          freq: 0.35 + Math.random() * 1.2,
        })
      })
    })
    targets.current = found
    baseData.current = base
  }, [root])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    for (let i = 0; i < targets.current.length; i++) {
      const c = targets.current[i]
      const b = baseData.current[i]
      if (!c || !b) continue
      const wave =
        1 +
        0.14 * Math.sin(t * b.freq + b.phase) +
        0.08 * Math.sin(t * b.freq * 2.7 + b.phase * 1.7)
      // Rare flicker — quick dim drop
      const flickerSeed =
        Math.sin(t * 11 + b.phase * 3.1) * Math.sin(t * 6.5 + b.phase * 1.3)
      const flicker = flickerSeed > 0.96 ? 0.55 : 1
      c.setRGB(b.r * wave * flicker, b.g * wave * flicker, b.b * wave * flicker)
    }
  })

  return null
}

// ─────────────────────────────────────────────────────────────────────
// CityContainer — wraps CityModel, exposes the loaded scene for flicker.
// Compensates the source-model's offset so the city is horizontally
// centred around x=0.
// ─────────────────────────────────────────────────────────────────────
function CityContainer({ scale, position }) {
  const [scene, setScene] = useState(null)
  const offset = [
    position[0] - CITY_SOURCE_CENTER[0] * scale,
    position[1] - CITY_SOURCE_CENTER[1] * scale,
    position[2] - CITY_SOURCE_CENTER[2] * scale,
  ]
  return (
    <>
      <CityModel scale={scale} position={offset} onReady={setScene} />
      {scene && <NeonFlicker root={scene} />}
    </>
  )
}

// ─────────────────────────────────────────────────────────────────────
// BuildingBillboards — neon text glued ONTO building facades.
// Thin sign planes at building surface positions. NO floating squares.
// ─────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────

// ── Rich Billboard Data ──
const BB_TYPES = [
  { title:'IFODA',    sub:'AGRO SCIENCE',   bg:'#0a0020', fg:'#00f0ff', accent:'#ff2bd6' },
  { title:'NETRUNNER',sub:'v1.0 ONLINE',     bg:'#050015', fg:'#ff2bd6', accent:'#00f0ff' },
  { title:'東京',      sub:'CYBER DISTRICT', bg:'#0a0018', fg:'#fcee0a', accent:'#ff7a00' },
  { title:'DATA',      sub:'UPLINK ACTIVE',  bg:'#02081a', fg:'#00ff88', accent:'#00f0ff' },
  { title:'AGRO',      sub:'РЕАГЕНТЫ',       bg:'#080015', fg:'#ff7a00', accent:'#fcee0a' },
  { title:'24/7',      sub:'OPEN CIRCUIT',   bg:'#051000', fg:'#00ff88', accent:'#fcee0a' },
  { title:'КАФЕ',      sub:'НОЧНАЯ СМЕНА',   bg:'#150010', fg:'#ff2e4c', accent:'#ff2bd6' },
  { title:'СВЕТ',      sub:'NEON DISTRICT',  bg:'#0a000a', fg:'#a06bff', accent:'#ff2bd6' },
  { title:'CYBER',     sub:'TECH IMPORT',    bg:'#001015', fg:'#00f0ff', accent:'#00ff88' },
  { title:'DRINK',     sub:'SYNTH BAR',      bg:'#0a0500', fg:'#ff7a00', accent:'#fcee0a' },
  { title:'CLUB',      sub:'UNDERGROUND',    bg:'#100010', fg:'#ff2bd6', accent:'#a06bff' },
  { title:'電気',      sub:'POWER GRID',     bg:'#000818', fg:'#fcee0a', accent:'#00f0ff' },
  { title:'酒',        sub:'IZAKAYA BAR',    bg:'#0a0005', fg:'#ff2e4c', accent:'#ff7a00' },
  { title:'未来',      sub:'FUTURE CORP',    bg:'#000515', fg:'#a06bff', accent:'#00f0ff' },
  { title:'営業中',    sub:'OPEN 24H',       bg:'#050a00', fg:'#00ff88', accent:'#fcee0a' },
  { title:'最強',      sub:'MAX POWER',      bg:'#0a0200', fg:'#ff7a00', accent:'#ff2e4c' },
  { title:'NEON',      sub:'LIGHT DISTRICT', bg:'#0a000a', fg:'#ff2bd6', accent:'#00f0ff' },
  { title:'VOID',      sub:'DEEP NET',       bg:'#000510', fg:'#00f0ff', accent:'#a06bff' },
]

/**
 * generateBillboardTexture — renders a rich billboard panel on canvas.
 * Includes: gradient background, border frame, title, subtitle, decorative scanlines, corner marks.
 */
function generateBillboardTexture(bb, w = 1024, h = 320) {
  const c = document.createElement('canvas'); c.width = w; c.height = h
  const ctx = c.getContext('2d')
  ctx.imageSmoothingEnabled = true

  // Dark background
  ctx.fillStyle = bb.bg
  ctx.fillRect(0, 0, w, h)

  // Gradient overlay
  const grad = ctx.createLinearGradient(0, h, 0, 0)
  grad.addColorStop(0, bb.fg + '18')
  grad.addColorStop(0.35, bb.accent + '08')
  grad.addColorStop(0.7, 'transparent')
  grad.addColorStop(1, bb.fg + '0c')
  ctx.fillStyle = grad; ctx.fillRect(0, 0, w, h)

  // Border frame
  ctx.strokeStyle = bb.fg + '99'; ctx.lineWidth = 5
  ctx.strokeRect(10, 8, w - 20, h - 16)
  ctx.strokeStyle = bb.accent + '66'; ctx.lineWidth = 2
  ctx.strokeRect(16, 14, w - 32, h - 28)

  // Corner brackets
  const cr = 28; ctx.strokeStyle = bb.fg; ctx.lineWidth = 3
  ctx.beginPath(); ctx.moveTo(16, cr); ctx.lineTo(16, 14); ctx.lineTo(cr, 14); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(w - cr, 14); ctx.lineTo(w - 16, 14); ctx.lineTo(w - 16, cr); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(16, h - cr); ctx.lineTo(16, h - 14); ctx.lineTo(cr, h - 14); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(w - cr, h - 14); ctx.lineTo(w - 16, h - 14); ctx.lineTo(w - 16, h - cr); ctx.stroke()

  // Scanlines
  ctx.fillStyle = bb.fg + '05'
  for (let y = 0; y < h; y += 4) { ctx.fillRect(0, y, w, 1) }

  // Title — bold, crisp, no blur
  const titleY = h * 0.38
  ctx.font = '900 130px "Arial Black", "Impact", "Arial", sans-serif'
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.shadowBlur = 0
  ctx.fillStyle = '#ffffff'
  ctx.fillText(bb.title, w / 2, titleY)

  // Subtitle
  const subY = h * 0.70
  ctx.font = '900 48px "Arial Black", "Arial", sans-serif'
  ctx.fillStyle = bb.accent
  ctx.fillText(bb.sub, w / 2, subY)

  // Status dot
  ctx.fillStyle = bb.fg; ctx.beginPath()
  ctx.arc(w - 40, 24, 10, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = bb.fg + '30'; ctx.beginPath()
  ctx.arc(w - 40, 24, 18, 0, Math.PI * 2); ctx.fill()

  const t = new THREE.CanvasTexture(c); t.needsUpdate = true
  t.minFilter = THREE.LinearFilter; t.magFilter = THREE.LinearFilter
  return t
}

function WallSign({ position, bb, width = 5, height = 1.5, facing = 0 }) {
  const tex = useMemo(() => generateBillboardTexture(bb, 1024, Math.round(1024 * (height / width))), [bb, width, height])
  return (
    <group position={position} rotation={[0, facing, 0]}>
      {/* Main billboard face */}
      <mesh position={[0, 0, 0.04]}>
        <planeGeometry args={[width, height]} />
        <meshBasicMaterial map={tex} transparent depthWrite={false} toneMapped={false} />
      </mesh>
      {/* Glow panel behind */}
      <mesh position={[0, 0, -0.01]}>
        <planeGeometry args={[width * 1.15, height * 1.2]} />
        <meshBasicMaterial color={bb.fg} transparent opacity={0.08} depthWrite={false} toneMapped={false} />
      </mesh>
      {/* Point light for local glow */}
      <pointLight color={bb.fg} intensity={0.5} distance={width * 2.2} />
    </group>
  )
}

function BuildingBillboards() {
  const signs = useMemo(() => {
    // Billboard positions ON the closest visible buildings.
    // Camera at [-1,7,26] looking at [0,5,-60], FOV 76°.
    // Buildings at x≈±6-8, z≈-2..-55.
    // Format: [x, y, z, width, typeIdx, height, facing]
    const pos = [
      // === CLOSEST ROW (z ≈ -2..-10) — BIG, eye-level ===
      [-7, 3, -3, 7, 0, 1.8, 0.18],            [8, 3, -3, 7, 1, 1.8, 2.96],
      [-7, 6, -6, 7.5, 2, 2.0, 0.18],           [8, 7, -6, 7.5, 3, 2.0, 2.96],
      [-7, 4, -9, 6.5, 4, 1.7, 0.15],           [8, 4, -9, 6.5, 5, 1.7, 2.99],
      // === ROW 2 (z ≈ -10..-18) — more density ===
      [-7, 5, -11, 7.5, 6, 2.0, 0.14],          [8, 6, -11, 7.5, 7, 2.0, 3.0],
      [-7, 9, -14, 8, 8, 2.2, 0.14],            [8, 9, -14, 8, 9, 2.2, 3.0],
      [-7, 6, -17, 7, 10, 1.8, 0.12],           [8, 7, -17, 7, 11, 1.8, 3.02],
      // === ROW 3 (z ≈ -18..-28) ===
      [-7, 5, -19, 6.5, 12, 1.7, 0.12],         [8, 5, -19, 6.5, 13, 1.7, 3.02],
      [-7, 11, -22, 7, 14, 1.9, 0.1],           [8, 11, -22, 7, 15, 1.9, 3.04],
      [-7, 8, -25, 6, 16, 1.6, 0.1],            [8, 9, -25, 6, 17, 1.6, 3.04],
      [-7, 6, -28, 7, 0, 1.8, 0.08],            [8, 7, -28, 7, 2, 1.8, 3.06],
      // === ROW 4 (z ≈ -30..-42) ===
      [-7, 10, -31, 6, 3, 1.6, 0.08],           [8, 11, -31, 6, 5, 1.6, 3.06],
      [-7, 13, -34, 5.5, 7, 1.5, 0.07],         [8, 14, -34, 5.5, 9, 1.5, 3.07],
      [-7, 8, -37, 6.5, 11, 1.7, 0.06],         [8, 9, -37, 6.5, 13, 1.7, 3.08],
      [-7, 12, -40, 5, 15, 1.4, 0.06],          [8, 12, -40, 5, 1, 1.4, 3.08],
      // === ROW 5 (z ≈ -42..-55) — deeper ===
      [-7, 10, -43, 5.5, 4, 1.5, 0.05],         [8, 11, -43, 5.5, 6, 1.5, 3.09],
      [-7, 15, -46, 5, 8, 1.4, 0.05],           [8, 16, -46, 5, 10, 1.4, 3.09],
      [-7, 9, -49, 6, 12, 1.6, 0.04],           [8, 10, -49, 6, 14, 1.6, 3.1],
      [-7, 12, -52, 5, 16, 1.4, 0.04],          [8, 13, -52, 5, 17, 1.4, 3.1],
      // === CENTER: extra-wide billboards across both sides ===
      [-1, 7, -8, 9, 0, 2.4, 0],                [2, 8, -20, 9, 6, 2.4, 3.14],
      [-1, 10, -32, 8, 12, 2.2, 0],              [2, 11, -44, 8, 3, 2.2, 3.14],
      // === VERTICAL strips (narrow, tall) ===
      [-7, 7, -5, 2, 4, 4.5, 0.18],             [8, 8, -5, 2, 10, 4.5, 2.96],
      [-7, 9, -15, 2.2, 15, 5, 0.14],            [8, 10, -15, 2.2, 1, 5, 3.0],
      [-7, 8, -26, 2.2, 8, 5.5, 0.1],            [8, 9, -26, 2.2, 14, 5.5, 3.04],
      [-7, 11, -38, 2, 5, 4.5, 0.06],            [8, 12, -38, 2, 11, 4.5, 3.08],
      // === GROUND LEVEL signs (low, visible at street view) ===
      [-7, 1.5, -2, 5, 2, 1.4, 0.2],             [8, 1.5, -2, 5, 7, 1.4, 2.94],
      [-7, 2, -10, 5.5, 9, 1.5, 0.15],           [8, 2, -10, 5.5, 16, 1.5, 2.99],
      [-7, 1.8, -18, 5, 13, 1.3, 0.12],          [8, 1.8, -18, 5, 4, 1.3, 3.02],
    ]
    return pos.map((p, i) => {
      const bb = BB_TYPES[p[4] % BB_TYPES.length]
      return { id: i, position: [p[0], p[1], p[2]], bb, width: p[3], height: p[5], facing: p[6] }
    })
  }, [])
  return <group>{signs.map(s => <WallSign key={s.id} {...s} />)}</group>
}

function Rain({ count = 3600 }) {
  const meshRef = useRef()
  const rain = useMemo(() => {
    const arr = []
    for (let i = 0; i < count; i++) {
      arr.push({
        x: (Math.random() - 0.5) * 240,
        y: Math.random() * 90 - 20,
        z: -5 - Math.random() * 220,
        speed: 0.4 + Math.random() * 2.0,
        depth: 0.3 + Math.random() * 0.7,
      })
    }
    return arr
  }, [count])

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const positions = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      positions[i * 3 + 0] = rain[i].x
      positions[i * 3 + 1] = rain[i].y
      positions[i * 3 + 2] = rain[i].z
    }
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return g
  }, [count, rain])

  useFrame((_, delta) => {
    if (!meshRef.current) return
    const positions = meshRef.current.geometry.attributes.position
    for (let i = 0; i < rain.length; i++) {
      const r = rain[i]
      r.y -= r.speed * delta * 28 * r.depth
      if (r.y < -15) {
        r.y = 75 + Math.random() * 15
        r.x = (Math.random() - 0.5) * 240
      }
      positions.setXYZ(i, r.x, r.y, r.z)
    }
    positions.needsUpdate = true
  })

  return (
    <points ref={meshRef} geometry={geometry}>
      <pointsMaterial
        color="#8899cc"
        size={0.14}
        transparent
        opacity={0.65}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  )
}

// ─────────────────────────────────────────────────────────────────────
// SparkParticles — floating neon embers / dust in the foreground
// ─────────────────────────────────────────────────────────────────────
function SparkParticles({ count = 300 }) {
  const meshRef = useRef()
  const particles = useMemo(() => {
    const arr = []
    for (let i = 0; i < count; i++) {
      arr.push({
        x: (Math.random() - 0.5) * 80,
        y: -5 + Math.random() * 50,
        z: -5 - Math.random() * 60,
        vx: (Math.random() - 0.5) * 0.3,
        vy: 0.1 + Math.random() * 0.6,
        vz: (Math.random() - 0.5) * 0.2,
        life: Math.random(),
        color: NEON_LIST[Math.floor(Math.random() * NEON_LIST.length)],
        size: 0.04 + Math.random() * 0.12,
      })
    }
    return arr
  }, [count])

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const positions = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      positions[i * 3 + 0] = particles[i].x
      positions[i * 3 + 1] = particles[i].y
      positions[i * 3 + 2] = particles[i].z
    }
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return g
  }, [count, particles])

  useFrame((_, delta) => {
    if (!meshRef.current) return
    const positions = meshRef.current.geometry.attributes.position
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i]
      p.life -= delta * 0.15
      p.y += p.vy * delta * 3
      p.x += p.vx * delta * 3 + Math.sin(p.life * 8) * 0.02
      p.z += p.vz * delta * 3
      if (p.life <= 0 || p.y > 45 || p.y < -5) {
        p.x = (Math.random() - 0.5) * 80
        p.y = -5 + Math.random() * 3
        p.z = -5 - Math.random() * 60
        p.life = 0.7 + Math.random() * 0.3
        p.color = NEON_LIST[Math.floor(Math.random() * NEON_LIST.length)]
      }
      positions.setXYZ(i, p.x, p.y, p.z)
    }
    positions.needsUpdate = true
  })

  return (
    <points ref={meshRef} geometry={geometry}>
      <pointsMaterial
        size={0.15}
        transparent
        opacity={0.55}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        vertexColors={false}
      >
        {/* Use per-particle coloring via a shader would be ideal, but for performance we use one shared color */}
        <color attach="color" args={['#ffaacc']} />
      </pointsMaterial>
    </points>
  )
}

// ─────────────────────────────────────────────────────────────────────
// DataDome — holographic wireframe hemisphere over the city.
// Subtle cyan rings + vertical arcs, like a city-wide data shield.
// ─────────────────────────────────────────────────────────────────────
function DataDome({ radius = 80, height = 25 }) {
  const groupRef = useRef()

  const domeGeo = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const pts = []
    // Horizontal rings
    const rings = 8
    const segs = 80
    for (let r = 0; r < rings; r++) {
      const y = (r / (rings - 1)) * height
      const rScale = Math.sqrt(1 - (y / height) ** 2) * radius
      for (let i = 0; i <= segs; i++) {
        const angle = (i / segs) * Math.PI * 2
        pts.push(Math.cos(angle) * rScale, y, Math.sin(angle) * rScale - 80)
      }
    }
    // Vertical arcs
    const arcs = 16
    for (let a = 0; a < arcs; a++) {
      const angle = (a / arcs) * Math.PI * 2
      for (let j = 0; j <= 30; j++) {
        const t = j / 30
        const y = t * height
        const rScale = Math.sqrt(1 - (y / height) ** 2) * radius
        pts.push(Math.cos(angle) * rScale, y, Math.sin(angle) * rScale - 80)
      }
    }
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    return g
  }, [radius, height])

  useFrame(({ clock }) => {
    if (!groupRef.current) return
    groupRef.current.rotation.y = Math.sin(clock.getElapsedTime() * 0.08) * 0.05
  })

  return (
    <group ref={groupRef}>
      <lineSegments geometry={domeGeo}>
        <lineBasicMaterial
          color="#00f0ff"
          transparent
          opacity={0.06}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>
    </group>
  )
}

// ─────────────────────────────────────────────────────────────────────
// CityLoadingFallback — shown while GLB loads
// ─────────────────────────────────────────────────────────────────────
function CityLoadingFallback() {
  return (
    <Html fullscreen>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', width: '100vw',
        fontFamily: 'var(--font-mono)',
        color: 'var(--color-neon-cyan)',
        fontSize: '0.85rem',
        letterSpacing: '0.2em',
        textShadow: '0 0 8px var(--color-neon-cyan)',
        pointerEvents: 'none',
        userSelect: 'none',
      }}>
        ⚡ RENDERING NIGHT CITY...
      </div>
    </Html>
  )
}

// ─────────────────────────────────────────────────────────────────────
// Main scene
// ─────────────────────────────────────────────────────────────────────
export default function NightCity() {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        background: '#08041a',
      }}
    >
      <Canvas
        gl={{
          antialias: true,
          powerPreference: 'high-performance',
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.05,
        }}
        camera={{ position: [-1, 7, 55], fov: 76, near: 0.5, far: 1500 }}
        dpr={[1, 1.6]}
      >
        {/* Night City atmosphere — deep purple fog with neon horizon glow */}
        <color attach="background" args={['#060015']} />
        <fog attach="fog" args={['#1a0030', 40, 320]} />

        {/* Lighting: dramatic neon glow */}
        <ambientLight intensity={0.14} color="#0c0420" />
        {/* Foreground neon pools */}
        <pointLight position={[8, 12, -10]} color="#ff2bd6" intensity={6} distance={45} />
        <pointLight position={[-8, 8, -5]} color="#00f0ff" intensity={5} distance={35} />
        <pointLight position={[0, 20, -30]} color="#fcee0a" intensity={4} distance={40} />
        {/* Deep city billboard glow */}
        <pointLight position={[20, 18, -40]} color="#ff2bd6" intensity={10} distance={70} />
        <pointLight position={[-25, 12, -50]} color="#00f0ff" intensity={8} distance={60} />
        <pointLight position={[10, 20, -75]} color="#fcee0a" intensity={7} distance={55} />
        <pointLight position={[-15, 14, -90]} color="#ff2bd6" intensity={9} distance={65} />
        <pointLight position={[5, 8, -25]} color="#00ff88" intensity={3} distance={30} />
        <pointLight position={[-20, 6, -20]} color="#ff7a00" intensity={3} distance={28} />

        <CameraDolly />
        <SkyDome />
        <FogMist />

        {/* The pre-built cyberpunk city — close-up eye-level view */}
        <Suspense fallback={<CityLoadingFallback />}>
          <CityContainer scale={9} position={[0, 0, -55]} />
        </Suspense>

        {/* Procedural building rows flanking the GLB so we have a full skyline */}
        <DetailedBuildings />

        {/* Multi-coloured neon billboards scattered on the buildings */}
        <BuildingBillboards />

        {/* Foreground motion */}
        <SparkParticles count={300} />
        <Rain count={3600} />
        <DataDome />

        <EffectComposer multisampling={0}>
          <Bloom
            intensity={2.2}
            luminanceThreshold={0.3}
            luminanceSmoothing={0.55}
            mipmapBlur
            radius={0.95}
          />
          <ChromaticAberration offset={[0.0012, 0.0016]} />
          <Vignette eskil={false} offset={0.14} darkness={0.72} />
        </EffectComposer>
      </Canvas>
    </div>
  )
}