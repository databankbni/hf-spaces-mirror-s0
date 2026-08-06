import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'

// ─────────────────────────────────────────────────────────────────────
// Detailed Building Generator
//
// A CP2077/Night City building is NOT a single box — it's a stack of
// boxes of varying heights, antennas on the roof, balconies, integrated
// billboards glued to the facade, and a DENSE grid of windows with
// many lit + many dark.
//
// We achieve density without killing framerate via THREE.InstancedMesh:
// one mesh per window "lane", hundreds of instances attached to it.
// We use two InstancedMesh per side: lit windows (warm/yellow) and
// dark windows (low alpha) so we don't pay shader-per-instance cost.
// ─────────────────────────────────────────────────────────────────────

const NEON = ['#00f0ff', '#ff2bd6', '#fcee0a', '#00ff88', '#ff7a00', '#ff2e4c']
const BODY = ['#0d0d24', '#0f0f28', '#0a0a1e', '#111130', '#08081a', '#141438']
const WINDOW_LIT = ['#4da6ff', '#3388dd', '#66c2ff', '#2299ee', '#88d4ff', '#3399ff']
const WINDOW_DARK = '#080818'
const GLYPHS = 'アイウエイオンケシスツナニヌネハヒフヘホマミムメモヤユヨラリルレロワヲン中亜人公会出引区合場新明時来東京光電'

// Mulberry32 deterministic RNG — keeps the city stable between reloads
function mulberry32(seed) {
  let a = seed >>> 0
  return function () {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function makeSignTexture(text, color, opts = {}) {
  const fontSize = opts.fontSize || 180
  const width = opts.width || 1024
  const height = opts.height || 256
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, width, height)
  ctx.font = `bold ${fontSize}px "Share Tech Mono", monospace`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.shadowColor = color
  ctx.shadowBlur = 36
  ctx.fillStyle = '#fff'
  ctx.fillText(text, width / 2, height / 2)
  // Inner crispness
  ctx.shadowBlur = 10
  ctx.fillText(text, width / 2, height / 2)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

// ─────────────────────────────────────────────────────────────────────
// Single detailed building — produces a Group with body, superstructure,
// antennas, balconies, integrated facade signs, and a window grid.
//
// The window grid is exported as a flat list of {x, y, z, lit} coords that
// the parent <Buildings/> collects and renders via InstancedMesh.
// ─────────────────────────────────────────────────────────────────────
function generateBuilding(rand, side, index) {
  const x = side * (5.8 + rand() * 2.2)
  const z = -2 - index * 2.1 - rand() * 1.0

  const baseW = 1.6 + rand() * 1.8
  const baseD = 1.4 + rand() * 1.4
  const baseH = 5 + rand() * 9

  // Superstructure (a smaller box stacked on top)
  const hasSuper = rand() > 0.25
  const superW = baseW * (0.55 + rand() * 0.35)
  const superD = baseD * (0.55 + rand() * 0.35)
  const superH = 2.5 + rand() * 5
  const superOffsetX = (rand() - 0.5) * (baseW - superW) * 0.4

  // Antenna / spire on top
  const hasSpire = rand() > 0.4
  const spireH = rand() * 3 + 1

  // Roof details (water tanks, AC units)
  const roofDetails = []
  for (let i = 0; i < 3; i++) {
    if (rand() > 0.55) {
      roofDetails.push({
        x: (rand() - 0.5) * (superW * 0.7),
        z: (rand() - 0.5) * (superD * 0.7),
        w: 0.25 + rand() * 0.35,
        d: 0.25 + rand() * 0.35,
        h: 0.3 + rand() * 0.5,
      })
    }
  }

  const bodyColor = BODY[Math.floor(rand() * BODY.length)]
  const edgeColor = NEON[Math.floor(rand() * NEON.length)]
  const signColor = NEON[Math.floor(rand() * NEON.length)]
  const windowColor = WINDOW_LIT[Math.floor(rand() * WINDOW_LIT.length)]

  // Windows on the side facing the street
  const windows = []
  // We tile windows on the street-facing wall only — performance-friendly
  const wallW = baseW
  const wallH = baseH
  const cellW = 0.32
  const cellH = 0.55
  const cellS = cellW // alias used by superstructure windows below
  const cols = Math.max(2, Math.floor(wallW / cellW))
  const rows = Math.max(3, Math.floor(wallH / cellH))
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (rand() < 0.25) continue // some windows missing (variation)
      const wx =
        (c - (cols - 1) / 2) * cellW + (rand() - 0.5) * 0.04
      const wy =
        -wallH / 2 + cellH * 0.6 + r * cellH
      windows.push({
        x: wx,
        y: wy,
        lit: rand() > 0.22,
        warm: rand() > 0.15,
      })
    }
  }

  // Superstructure windows
  if (hasSuper) {
    const colsS = Math.max(2, Math.floor(superW / cellW))
    const rowsS = Math.max(2, Math.floor(superH / cellH))
    for (let r = 0; r < rowsS; r++) {
      for (let c = 0; c < colsS; c++) {
        if (rand() < 0.3) continue
        const wx =
          (c - (colsS - 1) / 2) * cellS + (rand() - 0.5) * 0.04
        const wy = -superH / 2 + cellH * 0.6 + r * cellH
        windows.push({
          x: wx + superOffsetX,
          y: wy + baseH / 2 + superH / 2,
          lit: rand() > 0.3,
          warm: rand() > 0.2,
        })
      }
    }
  }

  // Facade sign (integrated, glued to the wall)
  const hasFacadeSign = rand() > 0.25
  const facadeSign = hasFacadeSign
    ? {
        yOffset: (rand() - 0.5) * baseH * 0.5,
        w: baseW * (0.8 + rand() * 0.20),
        h: baseW * (0.50 + rand() * 0.40),
        color: signColor,
        textLen: 3 + Math.floor(rand() * 5),
      }
    : null

  // Balcony strip on a few floors
  const balconyFloors = []
  for (let i = 1; i < 6; i++) {
    if (rand() > 0.7) {
      balconyFloors.push(-baseH / 2 + i * (baseH / 6))
    }
  }

  // Side anti-aliasing: random pillars / antennas sticking out
  const sideAccent = rand() > 0.5

  return {
    x,
    z,
    baseW,
    baseD,
    baseH,
    hasSuper,
    superW,
    superD,
    superH,
    superOffsetX,
    hasSpire,
    spireH,
    roofDetails,
    bodyColor,
    edgeColor,
    windowColor,
    side,
    windows,
    facadeSign,
    balconyFloors,
    sideAccent,
  }
}

// ─────────────────────────────────────────────────────────────────────
// Windows: InstancedMesh — one per "lit" tone, one for dark.
// We collect windows from all buildings into a single InstancedMesh per side.
// ─────────────────────────────────────────────────────────────────────
function WindowInstances({ buildings }) {
  const litRef = useRef()
  const darkRef = useRef()
  const totalRef = useRef(0)

  const allWindows = useMemo(() => {
    const arr = []
    buildings.forEach((b, bIdx) => {
      b.windows.forEach((w) => {
        // Place window on the street-facing wall
        const sideSign = b.side > 0 ? 1 : -1
        const wallX = sideSign * (b.baseW / 2 + 0.012)
        arr.push({
          building: bIdx,
          x: b.x + wallX * sideSign, // position is already absolute on side
          y: w.y + b.baseH / 2 - 4,
          z: b.z,
          color: w.lit
            ? new THREE.Color(
                w.warm
                  ? b.windowColor
                  : '#88c4ff'
              )
            : new THREE.Color(WINDOW_DARK),
          lit: w.lit,
          scale: 0.22 + (w.warm ? 0.04 : 0),
        })
      })
    })
    return arr
  }, [buildings])

  // Position the InstancedMesh: each instance is a small quad placed at
  // the window's world position, rotated to face the street.
  useEffect(() => {
    const lit = litRef.current
    const dark = darkRef.current
    if (!lit || !dark) return

    const dummy = new THREE.Object3D()
    let litIdx = 0
    let darkIdx = 0
    allWindows.forEach((w) => {
      const building = buildings[w.building]
      const sideSign = building.side > 0 ? 1 : -1
      dummy.position.set(w.x, w.y, w.z)
      dummy.rotation.set(0, sideSign > 0 ? -Math.PI / 2 : Math.PI / 2, 0)
      dummy.scale.set(w.scale, w.scale * 1.5, 1)
      dummy.updateMatrix()
      if (w.lit) {
        lit.setMatrixAt(litIdx, dummy.matrix)
        lit.setColorAt(litIdx, w.color)
        litIdx++
      } else {
        dark.setMatrixAt(darkIdx, dummy.matrix)
        dark.setColorAt(darkIdx, w.color)
        darkIdx++
      }
    })
    lit.count = litIdx
    dark.count = darkIdx
    lit.instanceMatrix.needsUpdate = true
    dark.instanceMatrix.needsUpdate = true
    if (lit.instanceColor) lit.instanceColor.needsUpdate = true
    if (dark.instanceColor) dark.instanceColor.needsUpdate = true
    totalRef.current = litIdx + darkIdx
  }, [allWindows, buildings])

  return (
    <group>
      <instancedMesh
        ref={litRef}
        args={[undefined, undefined, 4000]}
        frustumCulled={false}
      >
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
      <instancedMesh
        ref={darkRef}
        args={[undefined, undefined, 4000]}
        frustumCulled={false}
      >
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial transparent opacity={0.18} toneMapped={false} />
      </instancedMesh>
    </group>
  )
}

// ─────────────────────────────────────────────────────────────────────
// Single building visual: body, superstructure, spire, roof details,
// facade sign, balconies, side accent
// ─────────────────────────────────────────────────────────────────────
function BuildingVisual({ b }) {
  const facadeSignTex = useMemo(() => {
    if (!b.facadeSign) return null
    const text = Array.from(
      { length: b.facadeSign.textLen },
      () => GLYPHS[Math.floor(Math.random() * GLYPHS.length)]
    ).join('')
    return makeSignTexture(text, b.facadeSign.color, {
      width: 768,
      height: 256,
      fontSize: 160,
    })
  }, [b.facadeSign])

  const sideSign = b.side > 0 ? 1 : -1
  const streetWallX = sideSign * (b.baseW / 2 + 0.015)

  return (
    <group position={[b.x, 0, b.z]}>
      {/* main body — with subtle emissive for backlit glow */}
      <mesh position={[0, b.baseH / 2 - 4, 0]}>
        <boxGeometry args={[b.baseW, b.baseH, b.baseD]} />
        <meshStandardMaterial color={b.bodyColor} roughness={0.65} metalness={0.35} emissive={b.edgeColor} emissiveIntensity={0.08} />
      </mesh>

      {/* Vertical corner edge lines — thin neon strips on building corners */}
      {[[-1,-1],[1,-1],[-1,1],[1,1]].map(([sx,sz],ci)=>(
        <mesh key={`ce${ci}`} position={[sx*(b.baseW/2+0.015), b.baseH/2-4, sz*(b.baseD/2+0.015)]}>
          <boxGeometry args={[0.025, b.baseH, 0.025]} />
          <meshBasicMaterial color={b.edgeColor} toneMapped={false} />
        </mesh>
      ))}

      {/* superstructure on top */}
      {b.hasSuper && (
        <group>
          <mesh position={[b.superOffsetX, b.baseH - 4 + b.superH / 2, 0]}>
            <boxGeometry args={[b.superW, b.superH, b.superD]} />
            <meshStandardMaterial color={b.bodyColor} roughness={0.65} metalness={0.35} emissive={b.edgeColor} emissiveIntensity={0.08} />
          </mesh>
          {/* Superstructure corner edges */}
          {[[-1,-1],[1,-1],[-1,1],[1,1]].map(([sx,sz],ci)=>(
            <mesh key={`se${ci}`} position={[b.superOffsetX+sx*(b.superW/2+0.015), b.baseH-4+b.superH/2, sz*(b.superD/2+0.015)]}>
              <boxGeometry args={[0.02, b.superH, 0.02]} />
              <meshBasicMaterial color={b.edgeColor} toneMapped={false} />
            </mesh>
          ))}
        </group>
      )}

      {/* slim LED line on roof */}
      <mesh position={[0, b.baseH - 4 + 0.005, 0]}>
        <boxGeometry args={[b.baseW * 0.95, 0.012, b.baseD * 0.95]} />
        <meshBasicMaterial color={b.edgeColor} toneMapped={false} />
      </mesh>
      {b.hasSuper && (
        <mesh
          position={[
            b.superOffsetX,
            b.baseH - 4 + b.superH + 0.005,
            0,
          ]}
        >
          <boxGeometry args={[b.superW * 0.9, 0.01, b.superD * 0.9]} />
          <meshBasicMaterial color={b.edgeColor} toneMapped={false} />
        </mesh>
      )}

      {/* spire / antenna */}
      {b.hasSpire && (
        <mesh
          position={[
            b.superOffsetX + (Math.random() - 0.5) * b.superW * 0.3,
            b.baseH - 4 + b.superH + b.spireH / 2,
            0,
          ]}
        >
          <cylinderGeometry args={[0.015, 0.025, b.spireH, 6]} />
          <meshStandardMaterial color="#1a1a22" metalness={0.9} />
        </mesh>
      )}
      {b.hasSpire && (
        <mesh
          position={[
            b.superOffsetX + (Math.random() - 0.5) * b.superW * 0.3,
            b.baseH - 4 + b.superH + b.spireH + 0.06,
            0,
          ]}
        >
          <sphereGeometry args={[0.06, 6, 6]} />
          <meshBasicMaterial color={b.edgeColor} toneMapped={false} />
        </mesh>
      )}

      {/* roof details (water tanks, AC units) */}
      {b.roofDetails.map((r, i) => (
        <mesh
          key={i}
          position={[
            b.superOffsetX + r.x,
            b.baseH - 4 + b.superH + r.h / 2,
            r.z,
          ]}
        >
          <boxGeometry args={[r.w, r.h, r.d]} />
          <meshStandardMaterial color="#15151f" roughness={0.85} />
        </mesh>
      ))}

      {/* balconies */}
      {b.balconyFloors.map((by, i) => (
        <mesh
          key={i}
          position={[
            streetWallX - sideSign * 0.08,
            by - 4,
            0,
          ]}
        >
          <boxGeometry args={[b.baseW * 0.95, 0.04, 0.2]} />
          <meshStandardMaterial color="#101018" roughness={0.8} />
        </mesh>
      ))}

      {/* facade sign (integrated into the building wall) */}
      {b.facadeSign && facadeSignTex && (
        <group
          position={[
            streetWallX,
            -4 + b.baseH / 2 + b.facadeSign.yOffset,
            0,
          ]}
          rotation={[0, sideSign > 0 ? -Math.PI / 2 : Math.PI / 2, 0]}
        >
          {/* sign background */}
          <mesh position={[0, 0, -0.02]}>
            <planeGeometry args={[b.facadeSign.w, b.facadeSign.h]} />
            <meshBasicMaterial
              color={b.facadeSign.color}
              transparent
              opacity={0.92}
              toneMapped={false}
            />
          </mesh>
          {/* sign halo (extends out a bit to bloom) */}
          <mesh position={[0, 0, -0.04]}>
            <planeGeometry args={[b.facadeSign.w * 1.6, b.facadeSign.h * 1.8]} />
            <meshBasicMaterial
              color={b.facadeSign.color}
              transparent
              opacity={0.16}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
          {/* glyph layer */}
          <mesh position={[0, 0, 0]}>
            <planeGeometry
              args={[b.facadeSign.w * 0.92, b.facadeSign.h * 0.78]}
            />
            <meshBasicMaterial
              map={facadeSignTex}
              transparent
              toneMapped={false}
              depthWrite={false}
            />
          </mesh>
        </group>
      )}

      {/* side accent: small vertical neon stripe on a side wall */}
      {b.sideAccent && (
        <mesh
          position={[
            -sideSign * (b.baseW / 2 + 0.005),
            b.baseH / 2 - 4,
            b.baseD / 2,
          ]}
        >
          <planeGeometry args={[0.05, b.baseH * 0.7]} />
          <meshBasicMaterial color={b.edgeColor} toneMapped={false} />
        </mesh>
      )}
    </group>
  )
}

// ─────────────────────────────────────────────────────────────────────
// Buildings + windows
// ─────────────────────────────────────────────────────────────────────
export default function Buildings() {
  const buildings = useMemo(() => {
    const arr = []
    // Deterministic per index so the city is reproducible
    for (let i = 0; i < 36; i++) {
      const rand = mulberry32(0xC0FFEE + i * 9973)
      const side = i % 2 === 0 ? 1 : -1
      arr.push(generateBuilding(rand, side, i))
    }
    return arr
  }, [])

  return (
    <group>
      {buildings.map((b, i) => (
        <BuildingVisual key={i} b={b} />
      ))}
      <WindowInstances buildings={buildings} />
    </group>
  )
}