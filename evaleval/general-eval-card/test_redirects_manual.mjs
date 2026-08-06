import { resolveModelRedirect } from "./lib/model-url-redirects.ts"
import { routeIdFromModelId } from "./lib/utils.ts"

// Test 1: Percent-encoding round-trip with special characters
const testIds = [
  "anthropic/claude-3.5-sonnet-20240620",  // has '.'
  "meta/Llama-3.1-8B",                      // has '.' and mixed case
  "01-ai/Yi-1.5-34B",                       // has '.' and '-' and digits
  "openai/gpt-4o",                          // lowercase with special combo
]

console.log("=== TEST 1: Percent-encoding round-trip ===")
testIds.forEach(id => {
  const encoded = routeIdFromModelId(id)
  const decoded = decodeURIComponent(encoded)
  const roundtrip = encoded.includes("%2F") ? "✓" : "✗ (slash not encoded!)"
  const match = decoded === id ? "✓" : "✗ (mismatch!)"
  console.log(`  ${id}`)
  console.log(`    -> encoded: ${encoded} ${roundtrip}`)
  console.log(`    -> decoded: ${decoded} ${match}`)
})

console.log("\n=== All manual tests completed ===")
