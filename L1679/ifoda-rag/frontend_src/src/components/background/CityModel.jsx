import { Gltf, useGLTF } from '@react-three/drei'
import { useRef, useEffect } from 'react'
import * as THREE from 'three'

/**
 * CityModel — loads the pre-built cyberpunk city scene from /models/city.glb.
 * Uses drei <Gltf> with no extra transforms (so the raw model loads 1:1).
 * Position is passed via Gltf's built-in props; scale too.
 */
export default function CityModel({
  position = [0, 0, 0],
  rotation = [0, 0, 0],
  scale = 1,
  onReady = null,
}) {
  const reported = useRef(false)
  return (
    <Gltf
      src="/models/city.glb"
      position={position}
      rotation={rotation}
      scale={scale}
      onLoad={(gltf) => {
        if (reported.current) return
        reported.current = true
        // Walk the scene and tweak materials for visibility — push emissive
        // intensity hard so neon glows even under low ambient.
        gltf.scene.traverse((obj) => {
          if (!obj.isMesh) return
          obj.castShadow = false
          obj.receiveShadow = false
          obj.frustumCulled = false
          obj.visible = true
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
          mats.forEach((m) => {
            if (!m) return
            m.needsUpdate = true
            if (m.side !== undefined) m.side = THREE.DoubleSide
            // Shift warm/yellow emissive to cool blue
            if (m.emissive && m.emissive.isColor) {
              const hsl = {}
              m.emissive.getHSL(hsl)
              if (hsl.h > 0.08 && hsl.h < 0.18 && hsl.s > 0.3) {
                m.emissive.setHSL(0.58, Math.min(hsl.s * 1.3, 1), Math.max(hsl.l, 0.3))
              }
              if (m.emissiveIntensity !== undefined) {
                m.emissiveIntensity = Math.max(m.emissiveIntensity || 0, 4.0)
              }
            }
            // Shift warm base color to cooler tone
            if (m.color && m.color.isColor) {
              const hsl2 = {}
              m.color.getHSL(hsl2)
              if (hsl2.h > 0.08 && hsl2.h < 0.18 && hsl2.s > 0.2 && hsl2.l > 0.3) {
                m.color.setHSL(0.57, hsl2.s * 0.9, hsl2.l * 0.85)
              }
            }
            if (m.toneMapped !== undefined) m.toneMapped = false
          })
        })
        // eslint-disable-next-line no-console
        console.log('[CityModel] raw load ready', gltf.scene.children.length, 'children')
        onReady?.(gltf.scene)
      }}
    />
  )
}

// Preload so the first frame already has the asset
useGLTF.preload('/models/city.glb')