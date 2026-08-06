const { addonBuilder, getRouter } = require("stremio-addon-sdk")
const express = require("express")
const path = require("path")
const fs = require("fs")

const manifest = {
    id: "local.subtitles.tr",
    version: "3.0.0",
    name: "Ensar Subtitles",
    description: "Türkçe anime altyazıları",
    logo: "https://i.imgur.com/dXk6IsE.jpeg",
    resources: ["subtitles"],
    types: ["series", "movie"],
    catalogs: [],
    idPrefixes: ["tt"]
}

const builder = new addonBuilder(manifest)

builder.defineSubtitlesHandler((args) => {
    console.log("ARGS:", JSON.stringify(args))

    const parts = args.id?.split(":")
const imdbId = parts?.[0]

const filenameMatch = args.extra?.filename?.match(/[\s._-](\d{1,4})[\s._\[-]/)
const epNum = filenameMatch ? parseInt(filenameMatch[1]) : parseInt(parts?.[2])

    console.log("IMDb ID:", imdbId, "Episode:", epNum)

    if (!imdbId || !epNum) return Promise.resolve({ subtitles: [] })

    const filename = `ep${epNum}.srt`
    const filePath = path.join(__dirname, "subtitles", imdbId, filename)

    if (!fs.existsSync(filePath)) {
        console.log("Dosya bulunamadı:", filePath)
        return Promise.resolve({ subtitles: [] })
    }

    return Promise.resolve({
        subtitles: [
            {
                id: `tr-${imdbId}-ep${epNum}`,
                lang: "tr",
                name: `TR Altyazı ep${epNum}`,
                url: `https://ob1one12-ensar-subtitles.hf.space/subs/${imdbId}/${filename}`
            }
        ]
    })
})

const app = express()

app.use("/subs", express.static(path.join(__dirname, "subtitles")))
app.use("/", getRouter(builder.getInterface()))

app.listen(7860, () => {
    console.log("Addon running on http://localhost:7860")
})
