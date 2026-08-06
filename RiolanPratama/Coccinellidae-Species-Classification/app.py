from flask import (Flask, render_template, request, session, redirect, url_for)
import os
import time
import uuid
import numpy as np

from PIL import Image

from werkzeug.utils import secure_filename

from tensorflow.keras.models import load_model
from tensorflow.keras.applications.efficientnet_v2 import preprocess_input

from languages.en import texts as en_texts
from languages.id import texts as id_texts

app = Flask(__name__)

app.secret_key = "skripsi_coccinellidae_secret_key_2026"

# =========================
# CONFIG
# =========================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "static",
    "uploads"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

# =========================
# LOAD MODEL
# =========================

MODEL_PATH = os.path.join(
    BASE_DIR,
    "models",
    "FineTuning_Final_Exp.keras"
)

model = load_model(MODEL_PATH)

# =========================
# CLASS NAMES
# =========================

class_names = [
    "Calvia Quatuordecimguttata",
    "Cheilomenes Sexmaculata",
    "Coccinella Septempunctata",
    "Coccinella Transversalis",
    "Exochomus Quadripustulatus",
    "Henosepilachna Vigintioctopunctata",
    "Hippodamia Variegata",
    "Propylea Quatuordecimpunctata",
    "Psyllobora Vigintimaculata",
    "Tytthaspis Sedecimpunctata"
]

IMG_SIZE = 512

UNKNOWN_THRESHOLD = 30
LOW_CONFIDENCE_THRESHOLD = 50

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

# =========================
# LANGUAGE
# =========================

LANGUAGES = {
    "en": en_texts,
    "id": id_texts
}

# =========================
# FILE VALIDATION
# =========================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


# =========================
# HOME
# =========================

@app.route("/", methods=["GET", "POST"])
def index():

    lang = request.args.get("lang", "en")

    if lang not in LANGUAGES:
        lang = "en"

    t = LANGUAGES[lang]

    # =========================
    # LOAD FROM SESSION
    # =========================

    prediction = session.get("prediction")
    confidence = session.get("confidence")
    image_path = session.get("image_path")
    prediction_time = session.get("prediction_time")

    top3_results = session.get("top3_results")
    all_predictions = session.get("all_predictions")

    if request.method == "POST":

        file = request.files.get("image")

        if (
            file
            and file.filename != ""
            and allowed_file(file.filename)
        ):

            filename = secure_filename(file.filename)

            extension = os.path.splitext(
                filename
            )[1].lower()

            filename = (
                f"{uuid.uuid4()}{extension}"
            )

            save_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            file.save(save_path)

            image_path = (
                f"/static/uploads/{filename}"
            )

            # =========================
            # PREPROCESSING
            # =========================

            try:

                img = Image.open(
                    save_path
                ).convert("RGB")

            except Exception:

                os.remove(save_path)

                return render_template(

                    "index.html",

                    prediction="Invalid Image File",

                    t=t,

                    lang=lang,

                    UNKNOWN_THRESHOLD=UNKNOWN_THRESHOLD,

                    LOW_CONFIDENCE_THRESHOLD=LOW_CONFIDENCE_THRESHOLD
                )

            img = img.resize(
                (IMG_SIZE, IMG_SIZE)
            )

            img_array = np.array(img)

            img_array = np.expand_dims(
                img_array,
                axis=0
            )

            img_array = preprocess_input(
                img_array
            )

            # =========================
            # PREDICTION
            # =========================

            start_time = time.time()

            preds = model.predict(
                img_array,
                verbose=0
            )

            end_time = time.time()

            prediction_time = round(
                end_time - start_time,
                3
            )

            preds = preds[0]

            pred_idx = np.argmax(preds)

            prediction = class_names[pred_idx]

            confidence = round(
                float(np.max(preds)) * 100,
                2
            )

            # =========================
            # UNKNOWN DETECTION
            # =========================

            if confidence < UNKNOWN_THRESHOLD:

                prediction = (
                    "Unknown Species / "
                    "Outside Registered Species"
                )

            # =========================
            # TOP 3
            # =========================

            top3_idx = np.argsort(
                preds
            )[-3:][::-1]

            top3_results = []

            for idx in top3_idx:

                top3_results.append(
                    {
                        "class": class_names[idx],
                        "confidence": round(
                            float(preds[idx]) * 100,
                            2
                        )
                    }
                )

            # =========================
            # ALL PROBABILITIES
            # =========================

            all_predictions = []

            for idx, prob in enumerate(preds):

                all_predictions.append(
                    {
                        "class": class_names[idx],
                        "confidence": round(
                            float(prob) * 100,
                            4
                        )
                    }
                )

            all_predictions = sorted(
                all_predictions,
                key=lambda x: x["confidence"],
                reverse=True
            )

            # =========================
            # SAVE RESULT TO SESSION
            # =========================

            session["prediction"] = prediction
            session["confidence"] = confidence
            session["image_path"] = image_path
            session["prediction_time"] = prediction_time
            session["top3_results"] = top3_results
            session["all_predictions"] = all_predictions

    return render_template(
        "index.html",
        prediction=prediction,
        confidence=confidence,
        image_path=image_path,
        prediction_time=prediction_time,
        top3_results=top3_results,
        all_predictions=all_predictions,
        UNKNOWN_THRESHOLD=UNKNOWN_THRESHOLD,
        LOW_CONFIDENCE_THRESHOLD=LOW_CONFIDENCE_THRESHOLD,
        t=t,
        lang=lang,
    )

# =========================
# NEW PREDICTION
# =========================

from flask import redirect, url_for

@app.route("/new_prediction")
def new_prediction():

    lang = request.args.get("lang", "en")

    session.clear()

    return redirect(
        url_for(
            "index",
            lang=lang
        )
    )

# =========================
# SPECIES
# =========================

@app.route("/species")
def species():

    lang = request.args.get("lang", "en")

    if lang not in LANGUAGES:
        lang = "en"

    t = LANGUAGES[lang]

    species_list = [

        {
            "name": "Calvia Quatuordecimguttata",

            "image": "/static/species/calvia.jpg",

            "short_description": {
                "en": "A cream-spotted ladybird commonly found in forests, shrubs, and woodland habitats across Europe and Asia.",
                "id": "Kumbang koksi bercak krem yang umum ditemukan di hutan, semak, dan kawasan berhutan di Eropa serta Asia."
            },

            "description": {
                "en": "Calvia quatuordecimguttata is a medium-sized ladybird distinguished by fourteen cream-colored spots on a maroon-brown body. Although the European form is the most common, this species exhibits several color variations in North America and parts of Asia. It inhabits forests, shrubs, and wooded areas where it actively preys on aphids and other small insects. Its glossy pronotum and distinctive abdominal coloration make it relatively easy to recognize among other ladybird beetles.",

                "id": "Calvia quatuordecimguttata merupakan kumbang koksi berukuran sedang yang memiliki empat belas bintik berwarna krem pada tubuh cokelat kemerahan. Meskipun bentuk yang ditemukan di Eropa merupakan yang paling umum, spesies ini memiliki beberapa variasi warna di Amerika Utara dan sebagian Asia. Habitatnya meliputi hutan, semak, dan kawasan berpohon, tempat spesies ini memangsa kutu daun serta serangga kecil lainnya. Pronotum yang mengilap dan warna khas pada bagian bawah tubuh menjadi ciri pembeda spesies ini."
            },

            "distribution": {
                "en": "Europe, North America, and Asia",
                "id": "Eropa, Amerika Utara, dan Asia"
            },

            "habitat": {
                "en": "Forests, shrubs, and woodland vegetation",
                "id": "Hutan, semak, dan vegetasi pepohonan"
            },

            "size": "4–5.5 mm"
        },

        {
            "name": "Cheilomenes Sexmaculata",

            "image": "/static/species/cheilomenes.jpg",

            "short_description": {
                "en": "A colorful ladybird widely distributed in tropical regions and frequently observed in agricultural landscapes.",
                "id": "Kumbang koksi berwarna cerah yang banyak ditemukan di daerah tropis dan lahan pertanian."
            },

            "description": {
                "en": "Cheilomenes sexmaculata is a widely distributed ladybird species found throughout tropical and subtropical regions of Asia. It exhibits several color morphs, making its appearance highly variable and sometimes difficult to distinguish from similar species. This beetle is well known as an effective natural predator of aphids and other soft-bodied insects, making it an important biological control agent in agriculture. It has also been introduced into several regions outside its native range for pest management.",

                "id": "Cheilomenes sexmaculata merupakan kumbang koksi yang tersebar luas di wilayah tropis dan subtropis Asia. Spesies ini memiliki berbagai variasi warna sehingga tampilannya cukup beragam dan terkadang sulit dibedakan dengan spesies lain yang mirip. Kumbang ini dikenal sebagai predator alami kutu daun dan berbagai serangga bertubuh lunak sehingga berperan penting sebagai agen pengendali hayati di bidang pertanian. Selain di habitat aslinya, spesies ini juga telah diperkenalkan ke beberapa wilayah lain untuk membantu pengendalian hama."
            },

            "distribution": {
                "en": "Asia, Australia, Caribbean, and South America",
                "id": "Asia, Australia, Karibia, dan Amerika Selatan"
            },

            "habitat": {
                "en": "Agricultural fields, gardens, and grasslands",
                "id": "Lahan pertanian, kebun, dan padang rumput"
            },

            "size": "5–8 mm"
        },

        {
            "name": "Coccinella Septempunctata",

            "image": "/static/species/septempunctata.jpg",

            "short_description": {
                "en": "The famous seven-spotted ladybird commonly inhabiting grasslands, forests, gardens, and agricultural ecosystems worldwide.",
                "id": "Kumbang koksi tujuh bintik yang terkenal dan banyak dijumpai di padang rumput, hutan, serta kebun."
            },

            "description": {
                "en": "Coccinella septempunctata, commonly known as the seven-spotted ladybird, is one of the most recognizable ladybird species in the world. It has orange-red wing covers with seven distinctive black spots and a black pronotum marked by two white patches. This species is commonly found in agricultural fields, grasslands, and gardens where it feeds primarily on aphids. Due to its effectiveness in reducing pest populations, it is widely regarded as an important beneficial insect.",

                "id": "Coccinella septempunctata atau kumbang koksi tujuh bintik merupakan salah satu spesies kumbang koksi yang paling mudah dikenali di dunia. Elytranya berwarna merah jingga dengan tujuh bintik hitam yang khas serta pronotum hitam yang memiliki dua bercak putih. Spesies ini banyak ditemukan di lahan pertanian, padang rumput, dan taman, tempat ia memangsa kutu daun sebagai sumber makanan utama. Kemampuannya dalam mengendalikan populasi hama menjadikannya salah satu serangga yang sangat bermanfaat bagi pertanian."
            },

            "distribution": {
                "en": "Europe, Asia, North America, and North Africa",
                "id": "Eropa, Asia, Amerika Utara, dan Afrika Utara"
            },

            "habitat": {
                "en": "Grasslands, farmlands, forests, and gardens",
                "id": "Padang rumput, lahan pertanian, hutan, dan kebun"
            },

            "size": "6.5–7.8 mm"
        },

        {
            "name": "Coccinella Transversalis",

            "image": "/static/species/transversalis.jpg",

            "short_description": {
                "en": "A brightly colored ladybird recognized by its distinctive transverse black bands across the red wing covers.",
                "id": "Kumbang koksi berwarna cerah dengan pola pita hitam melintang yang khas pada sayapnya."
            },

            "description": {
                "en": "Coccinella transversalis is a ladybird species distributed across South Asia, Southeast Asia, and Australia. It is recognized by its characteristic transverse markings on the wing covers and has long been studied due to its effectiveness as a natural predator. The species commonly inhabits agricultural ecosystems where it feeds on aphids and other small insect pests. Its wide geographical distribution reflects its adaptability to various environmental conditions.",

                "id": "Coccinella transversalis merupakan spesies kumbang koksi yang tersebar di Asia Selatan, Asia Tenggara, hingga Australia. Spesies ini dikenal melalui pola melintang yang khas pada elytranya dan telah lama dipelajari karena efektivitasnya sebagai predator alami. Habitatnya banyak ditemukan di lahan pertanian, tempat spesies ini memangsa kutu daun serta berbagai serangga hama berukuran kecil. Persebarannya yang luas menunjukkan kemampuannya beradaptasi dengan berbagai kondisi lingkungan."
            },

            "distribution": {
                "en": "India, Southeast Asia, Malesia, and Australia",
                "id": "India, Asia Tenggara, Malesia, dan Australia"
            },

            "habitat": {
                "en": "Agricultural fields, grasslands, and forests",
                "id": "Lahan pertanian, padang rumput, dan hutan"
            },

            "size": "5–7 mm"
        },

        {
            "name": "Exochomus Quadripustulatus",

            "image": "/static/species/exochomus.jpg",

            "short_description": {
                "en": "A small black ladybird with four reddish spots commonly inhabiting forests, shrubs, and deciduous trees.",
                "id": "Kumbang koksi hitam kecil dengan empat bercak merah yang hidup di hutan dan pepohonan."
            },

            "description": {
                "en": "Exochomus quadripustulatus, commonly called the pine ladybird, is a small, rounded ladybird commonly associated with coniferous trees. It usually has a shiny black body with four red, orange, or yellow spots, although the coloration may vary with age. This species is an important predator of aphids and scale insects found on pine trees and other conifers. Its distinctive appearance makes it relatively easy to identify among black-colored ladybird beetles.",

                "id": "Exochomus quadripustulatus atau pine ladybird merupakan kumbang koksi kecil berbentuk hampir bulat yang umumnya hidup pada pohon-pohon konifer. Tubuhnya biasanya berwarna hitam mengilap dengan empat bercak merah, jingga, atau kuning, meskipun warnanya dapat berubah seiring bertambahnya usia. Spesies ini merupakan predator penting bagi kutu daun dan kutu perisai yang hidup pada pohon pinus dan tumbuhan konifer lainnya. Pola warnanya yang khas menjadikannya mudah dikenali di antara kumbang koksi berwarna hitam."
            },

            "distribution": {
                "en": "Europe, Asia, and North Africa",
                "id": "Eropa, Asia, dan Afrika Utara"
            },

            "habitat": {
                "en": "Pine forests and coniferous woodlands",
                "id": "Hutan pinus dan hutan konifer"
            },

            "size": "4–6 mm"
        },

        {
            "name": "Henosepilachna Vigintioctopunctata",

            "image": "/static/species/henosepilachna.jpg",

            "short_description": {
                "en": "A phytophagous ladybird recognized by numerous black spots feeding mainly on solanaceous crop plants.",
                "id": "Kumbang koksi pemakan tumbuhan dengan banyak bintik hitam yang sering menyerang tanaman famili Solanaceae."
            },

            "description": {
                "en": "Henosepilachna vigintioctopunctata, commonly known as the 28-spotted potato ladybird, differs from many other ladybird species because it feeds on plant leaves rather than insects. It is considered an agricultural pest that attacks potatoes, eggplants, tomatoes, and other plants in the Solanaceae family. Adults have numerous black spots covering their yellowish-brown wing covers, making them easy to distinguish. This species is widely distributed throughout tropical and subtropical regions of Asia.",

                "id": "Henosepilachna vigintioctopunctata atau kumbang koksi kentang 28 bintik berbeda dari sebagian besar kumbang koksi lainnya karena memakan daun tumbuhan, bukan serangga. Spesies ini dikenal sebagai hama pertanian yang menyerang kentang, terong, tomat, dan tanaman lain dari famili Solanaceae. Imago memiliki banyak bintik hitam pada elytra berwarna kuning kecokelatan sehingga mudah dikenali. Spesies ini tersebar luas di wilayah tropis dan subtropis Asia."
            },

            "distribution": {
                "en": "Asia and Australia",
                "id": "Asia dan Australia"
            },

            "habitat": {
                "en": "Agricultural fields and vegetable plantations",
                "id": "Lahan pertanian dan perkebunan sayuran"
            },

            "size": "6–8 mm"
        },

        {
            "name": "Hippodamia Variegata",

            "image": "/static/species/hippodamia.jpg",

            "short_description": {
                "en": "A variable-colored ladybird commonly associated with crop fields, grasslands, and natural vegetation habitats.",
                "id": "Kumbang koksi dengan warna tubuh yang bervariasi dan umum ditemukan di lahan pertanian maupun padang rumput."
            },

            "description": {
                "en": "Hippodamia variegata, commonly known as the Adonis ladybird, is a small and elongated ladybird widely distributed across Europe, Asia, Africa, and Australia. Its orange or red wing covers display a highly variable number of black spots, making each individual slightly different in appearance. This species is an efficient predator of aphids and other soft-bodied insects, contributing significantly to natural pest control in agricultural ecosystems. It is commonly found in grasslands, crop fields, and gardens.",

                "id": "Hippodamia variegata atau Adonis ladybird merupakan kumbang koksi berukuran kecil dengan bentuk tubuh memanjang yang tersebar luas di Eropa, Asia, Afrika, dan Australia. Elytranya berwarna merah atau jingga dengan jumlah bintik hitam yang sangat bervariasi sehingga setiap individu dapat memiliki pola yang berbeda. Spesies ini merupakan predator efektif bagi kutu daun dan berbagai serangga bertubuh lunak sehingga berperan penting dalam pengendalian hama secara alami. Habitatnya meliputi padang rumput, lahan pertanian, dan taman."
            },

            "distribution": {
                "en": "Europe, Asia, Africa, and North America",
                "id": "Eropa, Asia, Afrika, dan Amerika Utara"
            },

            "habitat": {
                "en": "Grasslands, agricultural fields, and gardens",
                "id": "Padang rumput, lahan pertanian, dan kebun"
            },

            "size": "3–5.5 mm"
        },

        {
            "name": "Propylea Quatuordecimpunctata",

            "image": "/static/species/propylea.jpg",

            "short_description": {
                "en": "A yellow ladybird displaying fourteen black spots commonly found throughout grasslands and cultivated agricultural fields.",
                "id": "Kumbang koksi kuning dengan empat belas bintik hitam yang banyak ditemukan di lahan pertanian."
            },

            "description": {
                "en": "Propylea quatuordecimpunctata, often called the 14-spotted ladybird, is a small ladybird species recognized by its yellow to cream-colored body with black rectangular markings. The arrangement of these markings is highly variable, resulting in more than one hundred known color patterns. This species is commonly found in agricultural fields and grasslands where it feeds on aphids and other small insect pests. Its remarkable variation makes it one of the most visually diverse ladybird species.",

                "id": "Propylea quatuordecimpunctata atau kumbang koksi 14 bintik merupakan spesies berukuran kecil yang memiliki tubuh berwarna kuning hingga krem dengan bercak hitam berbentuk persegi. Pola bercaknya sangat bervariasi sehingga telah diketahui lebih dari seratus variasi warna dan pola. Spesies ini banyak ditemukan di lahan pertanian dan padang rumput sebagai predator kutu daun serta serangga hama berukuran kecil. Variasi pola tubuhnya menjadikannya salah satu spesies kumbang koksi yang paling beragam secara visual."
            },

            "distribution": {
                "en": "Europe, Asia, and North America",
                "id": "Eropa, Asia, dan Amerika Utara"
            },

            "habitat": {
                "en": "Agricultural fields, grasslands, and shrubs",
                "id": "Lahan pertanian, padang rumput, dan semak"
            },

            "size": "3.5–4.5 mm"
        },

        {
            "name": "Psyllobora Vigintimaculata",

            "image": "/static/species/psyllobora.jpg",

            "short_description": {
                "en": "A tiny pale ladybird feeding primarily on powdery mildew fungi growing on leaves and stems.",
                "id": "Kumbang koksi kecil berwarna pucat yang memakan jamur embun tepung pada berbagai jenis tanaman."
            },

            "description": {
                "en": "Psyllobora vigintimaculata, commonly known as the twenty-spotted lady beetle, is a small North American species that differs from most ladybirds because it primarily feeds on fungi such as powdery mildew. It has a pale white body decorated with numerous orange or dark spots, making it easily distinguishable from predatory ladybird species. This beetle contributes to plant health by reducing fungal growth on leaves rather than controlling insect pests. It is commonly found on trees, shrubs, and herbaceous plants.",

                "id": "Psyllobora vigintimaculata atau kumbang koksi dua puluh bintik merupakan spesies kecil asal Amerika Utara yang berbeda dari sebagian besar kumbang koksi karena lebih banyak memakan jamur seperti embun tepung daripada serangga. Tubuhnya berwarna putih pucat dengan banyak bintik jingga atau gelap yang menjadi ciri khasnya. Spesies ini membantu menjaga kesehatan tanaman dengan mengurangi pertumbuhan jamur pada daun. Habitatnya meliputi pepohonan, semak, dan berbagai tumbuhan herba."
            },

            "distribution": {
                "en": "North America",
                "id": "Amerika Utara"
            },

            "habitat": {
                "en": "Forests, shrubs, and gardens",
                "id": "Hutan, semak, dan kebun"
            },

            "size": "1.75–3 mm"
        },

        {
            "name": "Tytthaspis Sedecimpunctata",

            "image": "/static/species/tytthaspis.jpg",

            "short_description": {
                "en": "A pale cream-colored ladybird distinguished by sixteen black spots inhabiting open grassland and meadow environments.",
                "id": "Kumbang koksi krem pucat dengan enam belas bintik hitam yang hidup di padang rumput terbuka."
            },

            "description": {
                "en": "Tytthaspis sedecimpunctata, commonly known as the sixteen-spotted ladybird, is a small ladybird widely distributed across Europe, North Africa, and parts of Asia. It typically has a cream or beige body with sixteen dark spots, many of which may merge into elongated markings. Unlike many ladybird species, it feeds on aphids as well as pollen, fungi, mites, and other small organisms. During winter, large numbers of individuals often gather together on tree trunks, wooden posts, and other sheltered surfaces.",

                "id": "Tytthaspis sedecimpunctata atau kumbang koksi enam belas bintik merupakan spesies kecil yang tersebar luas di Eropa, Afrika Utara, dan sebagian Asia. Tubuhnya umumnya berwarna krem atau cokelat muda dengan enam belas bintik gelap yang sering kali menyatu membentuk garis memanjang. Selain memangsa kutu daun, spesies ini juga memakan serbuk sari, jamur, tungau, dan organisme kecil lainnya. Pada musim dingin, kumbang ini sering membentuk kelompok besar pada batang pohon, tiang kayu, atau tempat berlindung lainnya."
            },

            "distribution": {
                "en": "Europe, North Africa, Asia, and Western China",
                "id": "Eropa, Afrika Utara, Asia, dan Tiongkok Barat"
            },

            "habitat": {
                "en": "Grasslands, dry meadows, dunes, and marshy fields",
                "id": "Padang rumput, padang kering, bukit pasir, dan lahan rawa"
            },

            "size": "2–3 mm"
        }

    ]


    return render_template(
        "species.html",
        species_list=species_list,
        lang=lang,
        t=t
    )


# =========================
# ABOUT
# =========================

@app.route("/about")
def about():

    lang = request.args.get("lang", "en")

    if lang not in LANGUAGES:
        lang = "en"

    t = LANGUAGES[lang]

    return render_template(
        "about.html",
        lang=lang,
        t=t
    )

# =========================
# RUN APP
# =========================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=7860,
        debug=True
    )