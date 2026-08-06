require('dotenv').config({ override: true });
const express = require('express');
const cors = require('cors');
const XLSX = require('xlsx');
const { createClient } = require('@supabase/supabase-js');

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;
const supabase = (supabaseUrl && supabaseKey) ? createClient(supabaseUrl, supabaseKey) : null;

function cleanLetterNumber(letterNumber) {
  if (!letterNumber) return 'UNKNOWN';
  return letterNumber.replace(/[^a-zA-Z0-9]/g, '_').replace(/_+/g, '_');
}


const app = express();
const PORT = process.env.PORT || 7860;

app.use(cors());
app.use(express.json());

/**
 * Parse LPJ filename to extract branch_name and letter number.
 * Format: timestamp_LPJ_BRANCHNAME_NUM_DEPT_ROMAWI_YEAR_xlsx
 * Example: 1779679618681_LPJ_ANYAR_173_KMD_AUDIT_V_2026_xlsx
 *   branch_name = ANYAR
 *   letter = 173/KMD-AUDIT/V/2026
 */
function parseLpjFilename(filename) {
  // Remove file extension variations and trailing _xlsx
  const cleanName = filename.replace(/\.(xlsx|xls)$/i, '').replace(/_xlsx$/i, '');

  const parts = cleanName.split('_');

  // Find LPJ index
  const lpjIndex = parts.findIndex(p => p.toUpperCase() === 'LPJ');
  if (lpjIndex === -1) return null;

  // Parts after LPJ
  const afterLpj = parts.slice(lpjIndex + 1);
  if (afterLpj.length < 4) return null;

  // Find the first part that looks like a letter number (starts with digits, optionally followed by a letter)
  // e.g., '173', '138', '063a', '182'
  let numericIndex = -1;
  for (let i = 0; i < afterLpj.length; i++) {
    if (/^\d+[a-zA-Z]?$/.test(afterLpj[i])) {
      numericIndex = i;
      break;
    }
  }

  if (numericIndex === -1 || numericIndex === 0) return null;

  // Branch name is everything before the letter number
  let branchParts = afterLpj.slice(0, numericIndex);

  // Filter out "Addendum" and "Excel" (case-insensitive) if they exist
  branchParts = branchParts.filter(p => {
    const upper = p.toUpperCase();
    return upper !== 'ADDENDUM' && upper !== 'EXCEL';
  });

  const branchName = branchParts.join(' ').trim();
  const letterParts = afterLpj.slice(numericIndex);

  // letterParts example: [063a, KMD, AUDIT, II, 2026]
  // Goal: 063a/KMD-AUDIT/II/2026
  if (letterParts.length < 4) return null;

  const num = letterParts[0]; // 063a
  const year = letterParts[letterParts.length - 1]; // 2026
  const roman = letterParts[letterParts.length - 2]; // II
  const deptParts = letterParts.slice(1, letterParts.length - 2); // [KMD, AUDIT]
  const dept = deptParts.join('-'); // KMD-AUDIT

  const letter = `${num}/${dept}/${roman}/${year}`;

  return {
    branch_name: branchName,
    letter: letter,
  };
}

// ============================================================
// GET /api/pending-backup-months
// Returns distinct months for LPJ and UM Perdin that have pending backups
// ============================================================
app.get('/api/pending-backup-months', async (req, res) => {
  try {
    // 1. Fetch valid finance reviews
    const { data: rawReviews, error: reviewError } = await supabase
      .from('finance_lpj_review')
      .select('ref_id, ref_type, checklist, checklist_rev, comment')
      .eq('checklist', true);

    if (reviewError) return res.status(500).json({ error: true, detail: reviewError.message });

    const validReviews = rawReviews.filter(r => !r.comment || (r.comment && r.checklist_rev === true));
    
    // LPJ pending logic
    const { data: lpjSubmissions } = await supabase
      .from('lpj_submissions')
      .select('created_at, letter_number')
      .eq('status_approve', 'close')
      .neq('file_path', 'x')
      .not('file_path', 'is', null);

    const letterIds = validReviews.filter(r => r.ref_type === 'letter').map(r => r.ref_id);
    const addendumIds = validReviews.filter(r => r.ref_type === 'addendum').map(r => r.ref_id);

    const { data: lettersData } = await supabase.from('letter').select('assigment_letter').in('id', letterIds.length > 0 ? letterIds : [0]);
    const { data: addendumsData } = await supabase.from('addendum').select('assigment_letter').in('id', addendumIds.length > 0 ? addendumIds : [0]);

    const validLettersSet = new Set([
      ...(lettersData || []).map(l => l.assigment_letter),
      ...(addendumsData || []).map(a => a.assigment_letter)
    ]);

    const pendingLpj = (lpjSubmissions || []).filter(s => validLettersSet.has(s.letter_number));

    // Surat pending logic
    const allLpjNumbers = (lpjSubmissions || []).map(s => s.letter_number);
    const { data: validLettersData } = await supabase.from('letter').select('assigment_letter, lpj, created_at').in('assigment_letter', allLpjNumbers.length > 0 ? allLpjNumbers : ['UNKNOWN']);
    const { data: validAddendumsData } = await supabase.from('addendum').select('assigment_letter, lpj, created_at').in('assigment_letter', allLpjNumbers.length > 0 ? allLpjNumbers : ['UNKNOWN']);

    const pendingSurat = [];
    [...(validLettersData || []), ...(validAddendumsData || [])].forEach(item => {
      if (item.lpj && item.lpj !== 'x' && validLettersSet.has(item.assigment_letter)) {
        pendingSurat.push(item);
      }
    });

    const getMonthsWithCount = (arr) => {
      const monthCounts = {};
      arr.forEach(item => {
        if (item.created_at) {
          const m = item.created_at.substring(0, 7);
          monthCounts[m] = (monthCounts[m] || 0) + 1;
        }
      });
      return Object.entries(monthCounts)
        .map(([month, count]) => ({ month, count }))
        .sort((a, b) => a.month.localeCompare(b.month));
    };

    res.json({
      error: false,
      lpj: getMonthsWithCount(pendingLpj),
      surat: getMonthsWithCount(pendingSurat)
    });
  } catch (err) {
    console.error('Error in pending-backup-months:', err);
    res.status(500).json({ error: true, detail: err.message });
  }
});

// ============================================================
// POST /api/parse-lpj
// Reads all LPJ Excel files from Supabase Storage bucket,
// parses the LPJ tab to extract Total row budget values,
// and returns the results.
// ============================================================
app.post('/api/parse-lpj', async (req, res) => {
  try {
    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_KEY;

    if (!supabaseUrl || !supabaseKey) {
      return res.status(500).json({
        error: true,
        detail: 'SUPABASE_URL and SUPABASE_KEY environment variables are not set'
      });
    }

    const supabase = createClient(supabaseUrl, supabaseKey);

    // List root items in lpj-documents bucket
    const { data: rootItems, error: listError } = await supabase.storage
      .from('lpj-documents')
      .list('', { limit: 1000 });

    if (listError) {
      console.error('Error listing files:', listError);
      return res.status(500).json({ error: true, detail: `Failed to list files: ${listError.message}` });
    }

    if (!rootItems || rootItems.length === 0) {
      return res.json({ error: false, results: [], message: 'No files found in bucket' });
    }

    // Gather all files (including those inside 1-level deep folders)
    let allFiles = [];
    for (const item of rootItems) {
      // In Supabase, folders typically have id === null
      if (!item.id) {
        // It's a folder, list its contents
        const { data: subItems } = await supabase.storage
          .from('lpj-documents')
          .list(item.name, { limit: 1000 });
          
        if (subItems) {
          // Append folder path to the filename so download works correctly
          const filesInFolder = subItems
            .filter(f => f.id) // Only files
            .map(f => ({ ...f, name: `${item.name}/${f.name}`, originalName: f.name }));
          allFiles.push(...filesInFolder);
        }
      } else {
        // It's a file in root
        allFiles.push({ ...item, originalName: item.name });
      }
    }

    // Filter only LPJ Excel files
    const lpjFiles = allFiles.filter(f => {
      const name = f.originalName.toUpperCase();
      return name.includes('LPJ') && (name.endsWith('.XLSX') || name.endsWith('_XLSX'));
    });

    console.log(`Found ${lpjFiles.length} LPJ files out of ${allFiles.length} total files`);

    // Fetch existing filenames from database to skip already processed files
    const { data: existingData, error: existingError } = await supabase
      .from('audit_budget_realisasi')
      .select('filename');

    const existingFilenames = new Set(
      existingData && !existingError ? existingData.map(r => r.filename) : []
    );

    const newLpjFiles = lpjFiles.filter(f => !existingFilenames.has(f.originalName));
    console.log(`Skipping ${lpjFiles.length - newLpjFiles.length} already processed files. Processing ${newLpjFiles.length} new files.`);

    const results = [];
    const errors = [];

    // Helper to process a single file
    const processFile = async (file) => {
      try {
        const parsed = parseLpjFilename(file.originalName);
        if (!parsed) {
          errors.push({ filename: file.originalName, error: 'Failed to parse filename' });
          return;
        }

        const { data: fileData, error: downloadError } = await supabase.storage
          .from('lpj-documents')
          .download(file.name);

        if (downloadError) {
          errors.push({ filename: file.name, error: `Download failed: ${downloadError.message}` });
          return;
        }

        const arrayBuffer = await fileData.arrayBuffer();
        const buffer = Buffer.from(arrayBuffer);
        const workbook = XLSX.read(buffer, { type: 'buffer' });

        const lpjSheetName = workbook.SheetNames.find(name => name.toUpperCase().includes('LPJ'));
        if (!lpjSheetName) {
          errors.push({ filename: file.name, error: 'No LPJ sheet found' });
          return;
        }

        const sheet = workbook.Sheets[lpjSheetName];
        const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' });

        let transportasi = 0;
        let konsumsi = 0;
        let lain_lain = 0;
        let foundTotal = false;

        for (const row of rows) {
          const totalCellIndex = row.findIndex(cell => typeof cell === 'string' && cell.trim().toLowerCase() === 'total');
          if (totalCellIndex !== -1) {
            const valuesAfterTotal = row.slice(totalCellIndex + 1)
              .map(v => {
                if (typeof v === 'number') return v;
                if (typeof v === 'string') {
                  const trimmed = v.trim();
                  if (trimmed === '') return null; // Ignore empty merged cells
                  if (trimmed === '-' || trimmed === '.') return 0; // Treat hyphens as zero
                  const cleaned = trimmed.replace(/[^\d.-]/g, '');
                  const parsed = parseFloat(cleaned);
                  return isNaN(parsed) ? null : parsed;
                }
                return null;
              }).filter(v => v !== null);

            if (valuesAfterTotal.length >= 3) {
              transportasi = valuesAfterTotal[0] || 0;
              konsumsi = valuesAfterTotal[1] || 0;
              lain_lain = valuesAfterTotal[2] || 0;
              foundTotal = true;
              break;
            }
          }
        }

        if (!foundTotal) {
          errors.push({ filename: file.name, error: 'Total row not found in LPJ sheet' });
          return;
        }

        results.push({
          letter: parsed.letter,
          branch_name: parsed.branch_name,
          transportasi,
          konsumsi,
          lain_lain,
          filename: file.originalName
        });

        console.log(`✓ ${file.originalName}: ${parsed.branch_name} | ${parsed.letter}`);

      } catch (fileErr) {
        console.error(`✗ Error processing ${file.originalName}:`, fileErr.message);
        errors.push({ filename: file.originalName, error: fileErr.message });
      }
    };

    // Process files in batches to speed up and avoid HTTP timeout
    const BATCH_SIZE = 20;
    for (let i = 0; i < newLpjFiles.length; i += BATCH_SIZE) {
      const batch = newLpjFiles.slice(i, i + BATCH_SIZE);
      await Promise.all(batch.map(f => processFile(f)));
    }


    // Deduplicate results by letter to prevent "ON CONFLICT DO UPDATE command cannot affect row a second time"
    // If there are multiple files with the same letter, keep the last one processed
    const uniqueResultsMap = new Map();
    for (const item of results) {
      uniqueResultsMap.set(item.letter, item);
    }
    const deduplicatedResults = Array.from(uniqueResultsMap.values());

    // Bulk upsert into database if there are results
    let upsertedCount = 0;
    if (deduplicatedResults.length > 0) {
      const { data: upsertData, error: upsertError } = await supabase
        .from('audit_budget_realisasi')
        .upsert(deduplicatedResults, { onConflict: 'letter', returning: 'minimal' });

      if (upsertError) {
        console.error('Bulk upsert error:', upsertError);
        errors.push({ filename: 'Database', error: `Bulk upsert failed: ${upsertError.message}` });
      } else {
        upsertedCount = deduplicatedResults.length;
      }
    }

    res.json({
      error: false,
      results,
      errors: errors.length > 0 ? errors : undefined,
      summary: {
        total_files: lpjFiles.length,
        new_files: newLpjFiles.length,
        parsed: results.length,
        upserted: upsertedCount,
        failed: errors.length
      }
    });

  } catch (err) {
    console.error('Unexpected error in parse-lpj:', err);
    res.status(500).json({ error: true, detail: err.message || 'Unexpected server error' });
  }
});



// ============================================================
// POST /api/backup-lpj
// Fetches closed LPJ submissions and backs them up to OwnCloud
// ============================================================
app.post('/api/backup-lpj', async (req, res) => {
  try {
    const owncloudUrl = process.env.OWNCLOUD_URL;
    const owncloudUsername = process.env.OWNCLOUD_USERNAME;
    const owncloudPassword = process.env.OWNCLOUD_PASSWORD;

    if (!owncloudUrl || !owncloudUsername || !owncloudPassword) {
      return res.status(500).json({
        error: true,
        detail: 'OWNCLOUD_URL, OWNCLOUD_USERNAME, and OWNCLOUD_PASSWORD environment variables are not set'
      });
    }

    // Create WebDAV Client for OwnCloud
    const { createClient: createWebDAVClient } = await import('webdav');
    const webdavClient = createWebDAVClient(owncloudUrl, {
      username: owncloudUsername,
      password: owncloudPassword
    });

    const { startDate, endDate, returnCountOnly } = req.body;

    // 1. Fetch LPJ Submissions that are "close"
    let query = supabase
      .from('lpj_submissions')
      .select('*')
      .eq('status_approve', 'close')
      .neq('file_path', 'x')
      .not('file_path', 'is', null);

    if (startDate && endDate) {
      query = query
        .gte('created_at', `${startDate}T00:00:00.000Z`)
        .lte('created_at', `${endDate}T23:59:59.999Z`);
    }

    const { data: submissions, error: fetchError } = await query;

    if (fetchError) {
      console.error('Error fetching submissions:', fetchError);
      return res.status(500).json({ error: true, detail: `Failed to fetch submissions: ${fetchError.message}` });
    }

    if (!submissions || submissions.length === 0) {
      return res.json({ error: false, message: 'No closed LPJ submissions found for backup', results: [] });
    }

    // 2. Fetch valid finance reviews (checklist = true, comment is null OR checklist_rev = true)
    const { data: rawReviews, error: reviewError } = await supabase
      .from('finance_lpj_review')
      .select('ref_id, ref_type, checklist, checklist_rev, comment')
      .eq('checklist', true);

    if (reviewError) {
      console.error('Error fetching finance reviews:', reviewError);
      return res.status(500).json({ error: true, detail: `Failed to fetch finance reviews: ${reviewError.message}` });
    }

    const validReviews = rawReviews.filter(r => 
      !r.comment || (r.comment && r.checklist_rev === true)
    );

    const letterIds = validReviews.filter(r => r.ref_type === 'letter').map(r => r.ref_id);
    const addendumIds = validReviews.filter(r => r.ref_type === 'addendum').map(r => r.ref_id);

    // 3. Fetch corresponding assignment letters
    const { data: validLetters } = await supabase
      .from('letter')
      .select('assigment_letter')
      .in('id', letterIds.length > 0 ? letterIds : [0]);

    const { data: validAddendums } = await supabase
      .from('addendum')
      .select('assigment_letter')
      .in('id', addendumIds.length > 0 ? addendumIds : [0]);

    const validLetterNumbers = new Set([
      ...(validLetters || []).map(l => l.assigment_letter),
      ...(validAddendums || []).map(a => a.assigment_letter)
    ]);

    // 4. Filter submissions based on valid finance review logic
    const filteredSubmissions = submissions.filter(s => validLetterNumbers.has(s.letter_number));

    if (filteredSubmissions.length === 0) {
      console.log('No submissions met the finance review criteria (checklist=true, comment=null, status_approve=close)');
      return res.json({ error: false, message: 'No submissions met the finance review criteria (checklist=true, comment=null)', results: [] });
    }

    if (returnCountOnly) {
      return res.json({ error: false, count: filteredSubmissions.length });
    }

    // Prepare streaming response
    res.setHeader('Content-Type', 'application/x-ndjson');
    res.setHeader('Transfer-Encoding', 'chunked');
    
    const sendChunk = (data) => {
      res.write(JSON.stringify(data) + '\n');
    };

    console.log(`Found ${filteredSubmissions.length} LPJ submissions meeting all criteria to backup.`);
    sendChunk({ type: 'init', total: filteredSubmissions.length });

    const results = [];
    const errors = [];
    const OWNCLOUD_BASE_PATH = '/OPTIMA/BUCKET/LPJ';

    // Helper to ensure target directory exists in OwnCloud
    // WebDAV createDirectory might throw if it exists, so we catch it gracefully
    const ensureDirectoryExists = async (path) => {
      try {
        if (await webdavClient.exists(path) === false) {
           await webdavClient.createDirectory(path);
        }
      } catch (err) {
        console.log(`Note: directory ${path} might already exist or could not be created.`);
      }
    };

    // Attempt to ensure base directory exists (sometimes multiple nested folders need to be created one by one)
    await ensureDirectoryExists('/OPTIMA');
    await ensureDirectoryExists('/OPTIMA/BUCKET');
    await ensureDirectoryExists(OWNCLOUD_BASE_PATH);

    // 2. Process each submission
    for (const submission of filteredSubmissions) {
      try {
        if (!submission.file_path) {
          errors.push({ id: submission.id, error: 'No file_path in submission' });
          continue;
        }

        // Download from Supabase
        const { data: fileData, error: downloadError } = await supabase.storage
          .from('lpj-documents')
          .download(submission.file_path);

        if (downloadError) {
          errors.push({ id: submission.id, letter_number: submission.letter_number, error: `Download failed: ${downloadError.message}` });
          continue;
        }

        const arrayBuffer = await fileData.arrayBuffer();
        const buffer = Buffer.from(arrayBuffer);

        // Determine File Extension (usually .xlsx or .xls)
        let ext = 'xlsx';
        if (submission.file_name) {
          const parts = submission.file_name.split('.');
          if (parts.length > 1) {
            ext = parts.pop();
          }
        } else if (submission.file_path) {
          const parts = submission.file_path.split('.');
          if (parts.length > 1) {
            ext = parts.pop();
          }
        }

        // Clean Letter Number and Format New Name
        const cleanNumber = cleanLetterNumber(submission.letter_number);
        const newFileName = `LPJ_Closed_${cleanNumber}.${ext}`;
        const targetPath = `${OWNCLOUD_BASE_PATH}/${newFileName}`;

        // Upload to OwnCloud via WebDAV
        await webdavClient.putFileContents(targetPath, buffer, { overwrite: true });

        // Cleanup from Supabase Storage
        const { error: removeError } = await supabase.storage.from('lpj-documents').remove([submission.file_path]);
        if (removeError) console.error(`Failed to remove LPJ file from Supabase: ${removeError.message}`);

        // Update DB table to mark as backed up
        const { error: dbError } = await supabase.from('lpj_submissions').update({ file_path: 'x' }).eq('id', submission.id);
        if (dbError) throw new Error(`Failed to update LPJ DB: ${dbError.message}`);

        results.push({
          id: submission.id,
          letter_number: submission.letter_number,
          original_file: submission.file_name || submission.file_path,
          backup_path: targetPath,
          status: 'success'
        });

        console.log(`✓ Backed up ${submission.letter_number} -> ${targetPath}`);
        sendChunk({ type: 'progress', current: results.length + errors.length, total: filteredSubmissions.length, status: 'success', message: `Backed up ${submission.letter_number}` });
      } catch (procErr) {
        console.error(`✗ Error processing submission ${submission.id}:`, procErr.message);
        errors.push({ id: submission.id, letter_number: submission.letter_number, error: procErr.message });
        sendChunk({ type: 'progress', current: results.length + errors.length, total: filteredSubmissions.length, status: 'error', message: procErr.message });
      }
    }

    sendChunk({
      type: 'complete',
      error: false,
      message: 'Backup process completed',
      summary: {
        total_found: filteredSubmissions.length,
        successful_backups: results.length,
        failed: errors.length
      },
      results,
      errors: errors.length > 0 ? errors : undefined
    });
    res.end();

  } catch (err) {
    console.error('Unexpected error in backup-lpj:', err);
    res.status(500).json({ error: true, detail: err.message || 'Unexpected server error' });
  }
});

// ============================================================
// POST /api/backup-surat
// Fetches letter/addendum files linked to closed LPJ submissions
// ============================================================
app.post('/api/backup-surat', async (req, res) => {
  try {
    const owncloudUrl = process.env.OWNCLOUD_URL;
    const owncloudUsername = process.env.OWNCLOUD_USERNAME;
    const owncloudPassword = process.env.OWNCLOUD_PASSWORD;

    if (!owncloudUrl || !owncloudUsername || !owncloudPassword) {
      return res.status(500).json({ error: true, detail: 'OWNCLOUD credentials not set' });
    }

    const { createClient: createWebDAVClient } = await import('webdav');
    const webdavClient = createWebDAVClient(owncloudUrl, {
      username: owncloudUsername,
      password: owncloudPassword
    });

    const { startDate, endDate, returnCountOnly } = req.body;

    let query = supabase.from('lpj_submissions').select('letter_number');
    if (startDate && endDate) {
      query = query.gte('created_at', `${startDate}T00:00:00.000Z`).lte('created_at', `${endDate}T23:59:59.999Z`);
    }

    const { data: submissions, error: fetchError } = await query;
    if (fetchError) return res.status(500).json({ error: true, detail: fetchError.message });
    if (!submissions || submissions.length === 0) {
      console.log('No LPJ submissions found in that date range for backup-surat');
      return res.json({ error: false, message: 'No LPJ submissions found', results: [] });
    }

    // Fetch valid finance reviews
    const { data: rawReviews, error: reviewError } = await supabase
      .from('finance_lpj_review')
      .select('ref_id, ref_type, checklist, checklist_rev, comment')
      .eq('checklist', true);

    if (reviewError) return res.status(500).json({ error: true, detail: reviewError.message });

    const validReviews = rawReviews.filter(r => 
      !r.comment || (r.comment && r.checklist_rev === true)
    );

    const letterIds = validReviews.filter(r => r.ref_type === 'letter').map(r => r.ref_id);
    const addendumIds = validReviews.filter(r => r.ref_type === 'addendum').map(r => r.ref_id);

    const { data: rLetters } = await supabase.from('letter').select('assigment_letter').in('id', letterIds.length > 0 ? letterIds : [0]);
    const { data: rAddendums } = await supabase.from('addendum').select('assigment_letter').in('id', addendumIds.length > 0 ? addendumIds : [0]);

    const validReviewLetterNumbers = new Set([
      ...(rLetters || []).map(l => l.assigment_letter),
      ...(rAddendums || []).map(a => a.assigment_letter)
    ]);

    const filteredSubmissions = submissions.filter(s => validReviewLetterNumbers.has(s.letter_number));

    if (filteredSubmissions.length === 0) {
      return res.json({ error: false, message: 'No matching UM Perdin files met the finance review criteria.', results: [] });
    }

    const letterNumbers = filteredSubmissions.map(s => s.letter_number);
    const uniqueLetterNumbers = [...new Set(letterNumbers)];

    const { data: validLetters } = await supabase.from('letter').select('assigment_letter, lpj').in('assigment_letter', uniqueLetterNumbers.length > 0 ? uniqueLetterNumbers : ['UNKNOWN']);
    const { data: validAddendums } = await supabase.from('addendum').select('assigment_letter, lpj').in('assigment_letter', uniqueLetterNumbers.length > 0 ? uniqueLetterNumbers : ['UNKNOWN']);

    // Map assignment_letter to its lpj file URL
    const suratFileMap = new Map();
    (validLetters || []).forEach(l => { if (l.lpj && l.lpj !== 'x') suratFileMap.set(l.assigment_letter, { url: l.lpj, table: 'letter' }) });
    (validAddendums || []).forEach(a => { if (a.lpj && a.lpj !== 'x') suratFileMap.set(a.assigment_letter, { url: a.lpj, table: 'addendum' }) });

    // Find overlapping submissions
    const validTargetUrls = [];
    
    for (const num of uniqueLetterNumbers) {
      if (suratFileMap.has(num)) {
        const info = suratFileMap.get(num);
        validTargetUrls.push({ letter_number: num, url: info.url, table: info.table });
      }
    }

    if (validTargetUrls.length === 0) {
      console.log('No matching UM Perdin files found for the criteria (backup-surat)');
      return res.json({ error: false, message: 'No matching UM Perdin files found for the criteria.', results: [] });
    }

    if (returnCountOnly) {
      return res.json({ error: false, count: validTargetUrls.length });
    }

    // Prepare streaming response
    res.setHeader('Content-Type', 'application/x-ndjson');
    res.setHeader('Transfer-Encoding', 'chunked');
    
    const sendChunk = (data) => {
      res.write(JSON.stringify(data) + '\n');
    };

    sendChunk({ type: 'init', total: validTargetUrls.length });

    const results = [];
    const errors = [];
    const OWNCLOUD_BASE_PATH = '/OPTIMA/BUCKET/LPJ';

    const ensureDirectoryExists = async (path) => {
      try { if (await webdavClient.exists(path) === false) await webdavClient.createDirectory(path); } catch (err) {}
    };
    await ensureDirectoryExists('/OPTIMA');
    await ensureDirectoryExists('/OPTIMA/BUCKET');
    await ensureDirectoryExists(OWNCLOUD_BASE_PATH);

    for (const item of validTargetUrls) {
      try {
        let ext = 'xlsx';
        const urlParts = item.url.split('?')[0].split('.');
        if (urlParts.length > 1) ext = urlParts.pop();

        const cleanNumber = cleanLetterNumber(item.letter_number);
        const newFileName = `LPJ_LOCKED_${cleanNumber}.${ext}`;
        const targetPath = `${OWNCLOUD_BASE_PATH}/${newFileName}`;

        const fileExists = await webdavClient.exists(targetPath);
        
        if (fileExists) {
          console.log(`Skipped upload (already exists): ${targetPath}`);
        } else {
          const fileRes = await fetch(item.url);
          if (!fileRes.ok) throw new Error(`Failed to download from public URL (status ${fileRes.status})`);
          
          const arrayBuffer = await fileRes.arrayBuffer();
          const buffer = Buffer.from(arrayBuffer);
          await webdavClient.putFileContents(targetPath, buffer, { overwrite: true });
        }

        // Cleanup from Supabase Storage
        const publicStr = '/object/public/';
        if (item.url.includes(publicStr)) {
          const pathAfterPublic = item.url.split(publicStr)[1];
          const pathParts = pathAfterPublic.split('/');
          const bucket = pathParts.shift();
          const filePath = pathParts.join('/');
          
          const { error: removeError } = await supabase.storage.from(bucket).remove([filePath]);
          if (removeError) console.error(`Failed to remove file from Supabase: ${removeError.message}`);
        }

        // Update DB table to mark as backed up
        const { error: dbError } = await supabase.from(item.table).update({ lpj: 'x' }).eq('assigment_letter', item.letter_number);
        if (dbError) throw new Error(`Failed to update DB: ${dbError.message}`);

        results.push({
          letter_number: item.letter_number,
          original_file: item.url,
          backup_path: targetPath,
          status: fileExists ? 'skipped (already exists)' : 'success'
        });
        sendChunk({ type: 'progress', current: results.length + errors.length, total: validTargetUrls.length, status: 'success', message: `Backed up ${item.letter_number}` });
      } catch (err) {
        console.error(`✗ Error processing UM Perdin ${item.letter_number}:`, err.message);
        errors.push({ letter_number: item.letter_number, error: err.message });
        sendChunk({ type: 'progress', current: results.length + errors.length, total: validTargetUrls.length, status: 'error', message: err.message });
      }
    }

    sendChunk({
      type: 'complete',
      error: false,
      message: 'Backup UM Perdin completed',
      summary: { total_found: validTargetUrls.length, successful_backups: results.length, failed: errors.length },
      results,
      errors: errors.length > 0 ? errors : undefined
    });
    res.end();

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: true, detail: err.message });
  }
});



// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Root endpoint
app.get('/', (req, res) => {
  res.json({
    name: "LPJ Reader API",
    version: "1.0.0",
    status: "running",
    endpoints: {
      parse_lpj: {
        url: "/api/parse-lpj",
        method: "POST",
        description: "Parse all LPJ Excel files from Supabase Storage and extract budget realisasi data.",
      },
      backup_lpj: {
        url: "/api/backup-lpj",
        method: "POST",
        description: "Backups closed LPJ files from Supabase to OwnCloud.",
      },
      backup_surat: {
        url: "/api/backup-surat",
        method: "POST",
        description: "Backups UM Perdin files linked to closed LPJ submissions to OwnCloud.",
      }
    }
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`LPJ Reader API is running on port ${PORT}`);
});
