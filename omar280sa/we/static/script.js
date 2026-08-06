/* ---------------------------------------------------------
   script.js
   Vanilla JS. No frameworks, no build step.
   Handles: file selection/preview (click + drag-drop), uploading,
   progress state, result with size comparison, copy-to-clipboard,
   and light/dark appearance.
   --------------------------------------------------------- */

(function () {
    "use strict";

    const fileInput = document.getElementById("file-input");
    const fileDrop = document.getElementById("file-drop");
    const fileLabel = document.getElementById("file-label");
    const previewWrap = document.getElementById("preview-wrap");
    const preview = document.getElementById("preview");
    const removeFileBtn = document.getElementById("remove-file");

    const qualityInput = document.getElementById("quality");
    const qualityValue = document.getElementById("quality-value");
    const targetSizeInput = document.getElementById("target-size");
    const maxWidthInput = document.getElementById("max-width");

    const uploadBtn = document.getElementById("upload-btn");
    const uploadBtnLabel = document.getElementById("upload-btn-label");
    const progress = document.getElementById("progress");

    const result = document.getElementById("result");
    const resultUrl = document.getElementById("result-url");
    const resultMeta = document.getElementById("result-meta");
    const resultPreview = document.getElementById("result-preview");
    const copyBtn = document.getElementById("copy-btn");
    const copyBtnLabel = document.getElementById("copy-btn-label");

    const sizeBefore = document.getElementById("size-before");
    const sizeAfter = document.getElementById("size-after");
    const sizePct = document.getElementById("size-pct");
    const sizeBarFill = document.getElementById("size-bar-fill");

    const themeToggle = document.getElementById("theme-toggle");

    const DEFAULT_FILE_LABEL = "Drop an image, or click to choose";

    let selectedFile = null;
    let isUploading = false;

    // -----------------------------------------------------------
    // File selection + preview
    // -----------------------------------------------------------

    function handleFile(file) {
        if (!file || !file.type.startsWith("image/")) {
            setProgress("Please choose an image file.", "error");
            return;
        }

        selectedFile = file;
        fileLabel.textContent = file.name;
        fileLabel.title = file.name;
        uploadBtn.disabled = false;
        uploadBtnLabel.textContent = "Upload image";

        const reader = new FileReader();
        reader.onload = function (e) {
            preview.src = e.target.result;
            previewWrap.classList.remove("hidden");
        };
        reader.readAsDataURL(file);

        result.classList.add("hidden");
        setProgress("");
    }

    fileInput.addEventListener("change", function () {
        const file = fileInput.files[0];
        if (file) handleFile(file);
    });

    // Open the picker on Enter/Space when the drop zone has keyboard focus
    // (the label+input already handles click, this covers non-click activation).
    fileDrop.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInput.click();
        }
    });

    // Drag and drop
    ["dragenter", "dragover"].forEach(function (evt) {
        fileDrop.addEventListener(evt, function (e) {
            e.preventDefault();
            e.stopPropagation();
            fileDrop.classList.add("drag-over");
        });
    });

    ["dragleave", "drop"].forEach(function (evt) {
        fileDrop.addEventListener(evt, function (e) {
            e.preventDefault();
            e.stopPropagation();
            fileDrop.classList.remove("drag-over");
        });
    });

    fileDrop.addEventListener("drop", function (e) {
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (!file) return;

        try {
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
        } catch (err) {
            // DataTransfer construction isn't supported everywhere; the file
            // still uploads fine since handleFile() uses `file` directly.
        }
        handleFile(file);
    });

    // Remove selected file
    removeFileBtn.addEventListener("click", function (e) {
        e.preventDefault();
        selectedFile = null;
        fileInput.value = "";
        fileLabel.textContent = DEFAULT_FILE_LABEL;
        fileLabel.removeAttribute("title");
        previewWrap.classList.add("hidden");
        preview.src = "";
        uploadBtn.disabled = true;
        uploadBtnLabel.textContent = "Choose an image first";
        result.classList.add("hidden");
        setProgress("");
    });

    // -----------------------------------------------------------
    // Quality slider live label
    // -----------------------------------------------------------

    qualityInput.addEventListener("input", function () {
        qualityValue.textContent = qualityInput.value;
    });

    // -----------------------------------------------------------
    // Upload
    // -----------------------------------------------------------

    uploadBtn.addEventListener("click", async function () {
        if (!selectedFile || isUploading) return;

        isUploading = true;
        uploadBtn.disabled = true;
        const spinner = document.createElement("span");
        spinner.className = "spinner";
        uploadBtn.insertBefore(spinner, uploadBtnLabel);
        uploadBtnLabel.textContent = "Uploading…";

        result.classList.add("hidden");
        setProgress("Uploading…");

        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("quality", qualityInput.value);
        formData.append("target_size", targetSizeInput.value);
        formData.append("max_width", maxWidthInput.value);

        try {
            const response = await fetch("/upload", {
                method: "POST",
                body: formData,
            });

            let data;
            try {
                data = await response.json();
            } catch (parseErr) {
                setProgress("The server sent back something unexpected.", "error");
                return;
            }

            if (!response.ok || !data.success) {
                setProgress((data && data.error) || "Upload failed. Please try again.", "error");
                return;
            }

            setProgress("Done", "success");
            resultUrl.value = data.url;
            resultPreview.src = data.url;

            const originalKb = selectedFile.size / 1024;
            const finalKb = Number(data.size_kb);
            renderSizeCompare(originalKb, finalKb);

            resultMeta.textContent = "Uploaded via " + data.provider;
            result.classList.remove("hidden");
        } catch (err) {
            setProgress("Network error. Is the server running?", "error");
        } finally {
            spinner.remove();
            uploadBtn.disabled = false;
            uploadBtnLabel.textContent = "Upload image";
            isUploading = false;
        }
    });

    function setProgress(text, type) {
        progress.textContent = text;
        progress.className = "progress" + (type ? " " + type : "");
    }

    function renderSizeCompare(originalKb, finalKb) {
        function fmt(kb) {
            return kb >= 1024 ? (kb / 1024).toFixed(2) + " MB" : Math.round(kb) + " KB";
        }

        sizeBefore.textContent = Number.isFinite(originalKb) ? fmt(originalKb) : "—";
        sizeAfter.textContent = Number.isFinite(finalKb) ? fmt(finalKb) : "—";

        let pct = 0;
        if (Number.isFinite(originalKb) && originalKb > 0 && Number.isFinite(finalKb)) {
            pct = Math.max(0, Math.min(100, Math.round((1 - finalKb / originalKb) * 100)));
        }
        sizePct.textContent = "\u2212" + pct + "%";

        sizeBarFill.style.width = "0%";
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                sizeBarFill.style.width = pct + "%";
            });
        });
    }

    // -----------------------------------------------------------
    // Copy button
    // -----------------------------------------------------------

    copyBtn.addEventListener("click", async function () {
        if (!resultUrl.value) return;
        try {
            await navigator.clipboard.writeText(resultUrl.value);
            flashCopied();
        } catch (err) {
            try {
                resultUrl.select();
                document.execCommand("copy");
                flashCopied();
            } catch (fallbackErr) {
                setProgress("Couldn't copy automatically — select the link and copy it manually.", "error");
            }
        }
    });

    function flashCopied() {
        const original = copyBtnLabel.textContent;
        copyBtnLabel.textContent = "Copied";
        setTimeout(function () {
            copyBtnLabel.textContent = original;
        }, 1500);
    }

    // -----------------------------------------------------------
    // Appearance (persisted in localStorage, falls back to system)
    // -----------------------------------------------------------

    function applyTheme(theme) {
        if (theme === "dark") {
            document.body.setAttribute("data-theme", "dark");
        } else {
            document.body.removeAttribute("data-theme");
        }
    }

    let savedTheme = null;
    try {
        savedTheme = localStorage.getItem("theme");
    } catch (err) {
        // localStorage may be unavailable (e.g. privacy mode).
    }
    if (!savedTheme) {
        savedTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    applyTheme(savedTheme);

    themeToggle.addEventListener("click", function () {
        const isDark = document.body.getAttribute("data-theme") === "dark";
        const newTheme = isDark ? "light" : "dark";
        applyTheme(newTheme);
        try {
            localStorage.setItem("theme", newTheme);
        } catch (err) {
            // Ignore if storage isn't available.
        }
    });
})();