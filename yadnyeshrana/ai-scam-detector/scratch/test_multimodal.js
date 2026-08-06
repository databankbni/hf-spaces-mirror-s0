require('dotenv').config();
const detectorService = require('../src/services/detector');

async function main() {
  console.log('🧪 TESTING MULTIMODAL IMAGE SCANNING ENGINE');
  console.log('==================================================');

  // Tiny 1x1 pixel transparent PNG Base64 string
  const mockImageBase64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
  const mockImage = {
    data: mockImageBase64,
    mimeType: 'image/png'
  };

  const isGeminiConfigured = !!process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'your_gemini_api_key_here';
  console.log(`🤖 Gemini API Key configured: ${isGeminiConfigured ? 'YES (Live AI mode)' : 'NO (Mock mode fallback)'}`);
  console.log('--------------------------------------------------');

  console.log('📋 Running test: Image scanning with caption...');
  try {
    const result1 = await detectorService.detectScam(
      'Verify this official letter from Mumbai Police demanding immediate payment',
      '919876543210',
      mockImage
    );
    console.log('Result 1 Risk Level:', result1.riskLevel);
    console.log('Result 1 Confidence:', result1.confidence + '%');
    console.log('Result 1 Explanation:', result1.explanation);
    console.log('Result 1 Actions:', result1.actions);
    console.log('--------------------------------------------------');

    if (result1.riskLevel === 'HIGH') {
      console.log('✅ TEST 1 PASSED: Correctly identified high risk from image details.');
    } else {
      console.log('❌ TEST 1 FAILED: Expected HIGH risk.');
    }
  } catch (error) {
    console.error('❌ Test 1 crashed with error:', error.message);
  }

  console.log('\n📋 Running test: Image scanning with NO caption...');
  try {
    const result2 = await detectorService.detectScam(
      '',
      '919876543210',
      mockImage
    );
    console.log('Result 2 Risk Level:', result2.riskLevel);
    console.log('Result 2 Confidence:', result2.confidence + '%');
    console.log('Result 2 Explanation:', result2.explanation);
    console.log('Result 2 Actions:', result2.actions);
    console.log('--------------------------------------------------');

    if (result2.riskLevel === 'HIGH') {
      console.log('✅ TEST 2 PASSED: Correctly evaluated raw image without text caption.');
    } else {
      console.log('❌ TEST 2 FAILED: Expected HIGH risk.');
    }
  } catch (error) {
    console.error('❌ Test 2 crashed with error:', error.message);
  }
}

main().catch(err => {
  console.error('Fatal test execution error:', err);
});
