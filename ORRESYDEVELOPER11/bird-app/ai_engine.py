from functools import lru_cache
import glob
import hashlib
import math
import os
import warnings

import numpy as np
from PIL import Image, ImageFilter, ImageOps

warnings.filterwarnings("ignore", category=UserWarning, module="tensorflow")

IMAGE_SIZE = (224, 224)
MAX_IMAGES_PER_BIRD = 5
TOP_K = 5

tf = None
MobileNetV2 = None
preprocess_input = None
keras_image = None

def _lazy_import_tf():
    global tf, MobileNetV2, preprocess_input, keras_image
    if tf is not None:
        return
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as _tf
    tf = _tf
    from tensorflow.keras.applications import MobileNetV2 as _MobileNetV2
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input as _ppi
    from tensorflow.keras.preprocessing import image as _ki
    MobileNetV2 = _MobileNetV2
    preprocess_input = _ppi
    keras_image = _ki


@lru_cache(maxsize=1)
def _load_mobilenet():
    _lazy_import_tf()
    if MobileNetV2 is None:
        return None
    try:
        return MobileNetV2(weights="imagenet", include_top=False, pooling="avg", input_shape=(224, 224, 3))
    except Exception as e:
        print(f"[ai_engine] Failed to load MobileNetV2: {e}")
        return None


def _tensorflow_embedding(path_or_arr):
    model = _load_mobilenet()
    if model is None:
        return None
    try:
        if isinstance(path_or_arr, str):
            img = keras_image.load_img(path_or_arr, target_size=IMAGE_SIZE)
            img_array = keras_image.img_to_array(img)
        else:
            img_array = path_or_arr
        img_array = np.expand_dims(img_array, axis=0)
        img_array = preprocess_input(img_array)
        emb = model.predict(img_array, verbose=0)
        return emb.flatten().astype(np.float32)
    except Exception:
        return None


def _color_histogram(path_or_arr):
    try:
        if isinstance(path_or_arr, str):
            image = Image.open(path_or_arr).convert("RGB").resize(IMAGE_SIZE)
            arr = np.asarray(image).astype(np.float32) / 255.0
        else:
            arr = path_or_arr.astype(np.float32) / 255.0
            if arr.max() > 1.0:
                arr = arr / 255.0

        bins = 32
        hist_per_channel = []
        for channel in range(3):
            hist, _ = np.histogram(arr[:, :, channel], bins=bins, range=(0, 1), density=True)
            hist_per_channel.append(hist)
        combined = np.concatenate(hist_per_channel).astype(np.float32)
        norm = np.linalg.norm(combined)
        return combined / norm if norm else combined
    except Exception:
        return None


def _texture_features(path_or_arr):
    try:
        if isinstance(path_or_arr, str):
            image = Image.open(path_or_arr).convert("L").resize(IMAGE_SIZE)
            arr = np.asarray(image).astype("float32") / 255.0
        else:
            gray = np.mean(path_or_arr, axis=2).astype("float32") / 255.0
            arr = gray

        gy, gx = np.gradient(arr)
        magnitude = np.sqrt(gx * gx + gy * gy)
        hist, _ = np.histogram(magnitude, bins=24, range=(0, 0.5), density=True)
        hist = hist.astype(np.float32)
        norm = np.linalg.norm(hist)
        return hist / norm if norm else hist
    except Exception:
        return None


def _embedding(path):
    vec_tf = _tensorflow_embedding(path)
    vec_color = _color_histogram(path)
    vec_texture = _texture_features(path)

    if vec_tf is not None and vec_color is not None and vec_texture is not None:
        combined = np.concatenate([vec_tf * 2.0, vec_color, vec_texture * 0.5])
        combined = combined / (np.linalg.norm(combined) + 1e-10)
        return combined, "MobileNetV2 + color + texture (fused)"

    if vec_tf is not None:
        return vec_tf, "MobileNetV2 feature extractor"

    if vec_color is not None and vec_texture is not None:
        combined = np.concatenate([vec_color, vec_texture])
        combined = combined / (np.linalg.norm(combined) + 1e-10)
        return combined, "Color histogram + texture (fallback)"

    return vec_color, "Color histogram (basic)"


def _embedding_augmented(path):
    vecs = []

    base, model_name = _embedding(path)
    if base is None:
        return None, None

    vecs.append(base)

    try:
        img = Image.open(path).convert("RGB")
        aug_ops = [
            ("flip", lambda im: im.transpose(Image.FLIP_LEFT_RIGHT)),
            ("blur", lambda im: im.filter(ImageFilter.GaussianBlur(radius=1))),
            ("contrast", lambda im: ImageOps.autocontrast(im, cutoff=2)),
        ]
        for name, op in aug_ops:
            aug_img = op(img)
            aug_arr = np.asarray(aug_img.resize(IMAGE_SIZE)).astype(np.float32)
            v, _ = _embedding_from_array(aug_arr)
            if v is not None:
                vecs.append(v)
    except Exception:
        pass

    avg = np.mean(vecs, axis=0)
    norm = np.linalg.norm(avg)
    return (avg / norm).astype(np.float32) if norm else avg.astype(np.float32), model_name


def _embedding_from_array(arr):
    vec_tf = _tensorflow_embedding(arr)
    vec_color = _color_histogram(arr)
    vec_texture = _texture_features(arr)

    if vec_tf is not None and vec_color is not None and vec_texture is not None:
        combined = np.concatenate([vec_tf * 2.0, vec_color, vec_texture * 0.5])
        combined = combined / (np.linalg.norm(combined) + 1e-10)
        return combined, "combined"

    if vec_tf is not None:
        return vec_tf, "tf_only"

    if vec_color is not None:
        return vec_color, "color_only"

    return None, None


def _all_images_for_bird(folder_name, project_root):
    folder = os.path.join(project_root, "dataset", "images", folder_name)
    if not os.path.isdir(folder):
        return []
    images = sorted(glob.glob(os.path.join(folder, "*.jpg")))
    return images[:MAX_IMAGES_PER_BIRD]


def _image_url_to_bird_folder(image_url):
    if not image_url or not image_url.startswith("/bird-image/"):
        return None
    parts = image_url.strip("/").split("/")
    if len(parts) != 3:
        return None
    return parts[1]


def _image_url_to_path(image_url, project_root):
    if not image_url or not image_url.startswith("/bird-image/"):
        return None
    parts = image_url.strip("/").split("/")
    if len(parts) != 3:
        return None
    _, folder, filename = parts
    path = os.path.join(project_root, "dataset", "images", folder, filename)
    return path if os.path.exists(path) else None


def precompute_reference_embeddings(birds, project_root, verbose=False):
    embeddings_by_bird_name = {}
    model_name_used = None

    for idx, bird in enumerate(birds):
        folder = _image_url_to_bird_folder(bird.image_url)
        if not folder:
            continue

        all_images = _all_images_for_bird(folder, project_root)
        if not all_images:
            single_path = _image_url_to_path(bird.image_url, project_root)
            if single_path:
                all_images = [single_path]

        bird_embeddings = []
        for img_path in all_images:
            vec, model_name = _embedding(img_path)
            if vec is not None:
                bird_embeddings.append(vec)
                if model_name_used is None:
                    model_name_used = model_name

        if bird_embeddings:
            embeddings_by_bird_name[bird.common_name] = np.array(bird_embeddings, dtype=np.float32)

        if verbose and (idx + 1) % 10 == 0:
            print(f"[precompute] embedded {idx + 1}/{len(birds)} birds")

    return embeddings_by_bird_name, model_name_used


def _cosine_similarity(a, b):
    if np is not None:
        a_f = a.astype(np.float64).flatten()
        b_f = b.astype(np.float64).flatten()
        dot = np.dot(a_f, b_f)
        na = np.linalg.norm(a_f)
        nb = np.linalg.norm(b_f)
        return float(dot / ((na * nb) + 1e-10))
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / ((norm_a * norm_b) + 1e-10)


def _gradcam_heatmap(image_path, reference_embedding=None):
    if tf is None or MobileNetV2 is None:
        return None
    base_model = _load_mobilenet()
    if base_model is None:
        return None

    spatial_output = None
    for layer in reversed(base_model.layers):
        try:
            shape = layer.output.shape
        except Exception:
            continue
        if shape is not None and len(shape) == 4:
            spatial_output = layer.output
            break
    if spatial_output is None:
        return None

    grad_model = tf.keras.models.Model(inputs=base_model.inputs, outputs=[spatial_output, base_model.output])
    img = keras_image.load_img(image_path, target_size=IMAGE_SIZE)
    img_array = keras_image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)

    with tf.GradientTape() as tape:
        conv_out, emb = grad_model(img_array)
        if reference_embedding is not None:
            emb_dim = int(emb.shape[1])
            ref_vec = reference_embedding.reshape(1, -1)
            if ref_vec.shape[1] > emb_dim:
                ref_vec = ref_vec[:, :emb_dim]
            ref = tf.constant(ref_vec, dtype=tf.float32)
            loss = tf.reduce_sum(tf.nn.l2_normalize(emb, axis=1) * tf.nn.l2_normalize(ref, axis=1))
        else:
            loss = tf.reduce_sum(emb ** 2)

    grads = tape.gradient(loss, conv_out)
    pooled = tf.reduce_mean(grads, axis=(0, 1, 2))
    heatmap = tf.reduce_sum(tf.multiply(pooled, conv_out), axis=-1)
    heatmap = np.maximum(heatmap.numpy()[0], 0)
    hmin, hmax = heatmap.min(), heatmap.max()
    if hmax > hmin:
        heatmap = (heatmap - hmin) / (hmax - hmin)
    return heatmap


def generate_gradcam_heatmap(image_path, output_path, reference_embedding=None, alpha=0.4):
    heatmap = _gradcam_heatmap(image_path, reference_embedding)
    if heatmap is None:
        return None
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None

    original = Image.open(image_path).convert("RGB").resize(IMAGE_SIZE)
    heatmap_img = Image.fromarray(np.uint8(plt.cm.jet(heatmap)[:, :, :3] * 255))
    heatmap_img = heatmap_img.resize(IMAGE_SIZE, Image.Resampling.BILINEAR)
    overlay = Image.blend(original, heatmap_img, alpha=alpha)
    overlay.save(output_path)
    plt.close("all")
    return output_path


def _parse_exif(img_path):
    try:
        from PIL import ExifTags
        image = Image.open(img_path)
        exif_data = image._getexif()
        if not exif_data:
            return {}
        result = {}
        for tag_id, value in exif_data.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            result[tag_name] = value
        camera_info = {}
        if "Make" in result:
            camera_info["make"] = result["Make"]
        if "Model" in result:
            camera_info["model"] = result["Model"]
        if "ISOSpeedRatings" in result:
            camera_info["iso"] = int(result["ISOSpeedRatings"])
        if "FNumber" in result:
            fnum = result["FNumber"]
            try:
                camera_info["aperture"] = float(fnum) if not isinstance(fnum, tuple) else float(fnum[0]) / float(fnum[1])
            except Exception:
                pass
        if "ExposureTime" in result:
            et = result["ExposureTime"]
            try:
                camera_info["shutter"] = str(et) if not isinstance(et, tuple) else f"{int(et[0])}/{int(et[1])}s"
            except Exception:
                pass
        if "FocalLength" in result:
            fl = result["FocalLength"]
            try:
                camera_info["focal_length"] = float(fl) if not isinstance(fl, tuple) else float(fl[0]) / float(fl[1])
            except Exception:
                pass
        if "DateTimeOriginal" in result:
            camera_info["date"] = str(result["DateTimeOriginal"])
        if "Software" in result:
            camera_info["software"] = str(result["Software"])

        gps_info = result.get("GPSInfo")
        if gps_info:
            try:
                def _gps_to_decimal(values, ref):
                    d, m, s = float(values[0]), float(values[1]), float(values[2])
                    dec = d + m / 60.0 + s / 3600.0
                    if ref in ("S", "W"):
                        dec = -dec
                    return dec
                lat = gps_info.get(2)
                lat_ref = gps_info.get(1)
                lon = gps_info.get(4)
                lon_ref = gps_info.get(3)
                if lat and lat_ref and lon and lon_ref:
                    camera_info["latitude"] = _gps_to_decimal(lat, lat_ref)
                    camera_info["longitude"] = _gps_to_decimal(lon, lon_ref)
            except Exception:
                pass

        if camera_info:
            return {"camera": camera_info}
        return {}
    except Exception:
        return {}


def _enrich_with_exif(prediction, upload_path):
    exif = _parse_exif(upload_path)
    if exif:
        prediction.setdefault("exif", {})
        prediction["exif"].update(exif)
    return prediction


def predict_bird(upload_path, birds, project_root, reference_embeddings=None):
    upload_vector, model_name = _embedding_augmented(upload_path)
    if upload_vector is None:
        raise ValueError("Failed to extract features from the uploaded image.")

    all_scores = []

    if reference_embeddings is not None:
        for bird in birds:
            bird_embeddings = reference_embeddings.get(bird.common_name)
            if bird_embeddings is None or len(bird_embeddings) == 0:
                continue

            best_score = 0.0
            num = 0
            if bird_embeddings.ndim == 1:
                sim = _cosine_similarity(upload_vector, bird_embeddings)
                best_score = sim
                num = 1
            else:
                for ref_vec in bird_embeddings:
                    sim = _cosine_similarity(upload_vector, ref_vec)
                    if sim > best_score:
                        best_score = sim
                    num += 1

            all_scores.append((best_score, bird, num))
    else:
        for bird in birds:
            sample_path = _image_url_to_path(bird.image_url, project_root)
            if not sample_path:
                continue
            sample_vector, _ = _embedding_augmented(sample_path)
            if sample_vector is None:
                continue
            sim = _cosine_similarity(upload_vector, sample_vector)
            all_scores.append((sim, bird, 1))

    if not all_scores:
        raise ValueError("No Tanzania bird reference images are available for AI comparison.")

    all_scores.sort(key=lambda item: item[0], reverse=True)

    best_score, best_bird, _ = all_scores[0]
    second_score = all_scores[1][0] if len(all_scores) > 1 else 0.0
    margin = best_score / max(second_score, 1e-8)

    if best_score < 0.20 or (best_score < 0.50 and margin < 1.15):
        raise ValueError("Unknown Image")

    raw_scores = np.array([s for s, _, _ in all_scores], dtype=np.float64)

    # Min-max normalize to [0, 1] then softmax with temperature
    s_min, s_max = raw_scores.min(), raw_scores.max()
    if s_max > s_min:
        normed = (raw_scores - s_min) / (s_max - s_min)
    else:
        normed = np.ones_like(raw_scores) / len(raw_scores)
    temperature = 0.05
    exp_s = np.exp(normed / temperature)
    probs = exp_s / np.sum(exp_s)

    confidence = max(1, min(99, round(probs[0] * 100)))

    alternatives = []
    for i in range(1, min(4, len(all_scores))):
        alt_conf = max(1, min(99, round(probs[i] * 100)))
        alternatives.append({"bird": all_scores[i][1], "confidence": alt_conf})

    return {
        "bird": best_bird,
        "confidence": confidence,
        "alternatives": alternatives,
        "model_name": model_name,
    }


def secure_image_digest(filepath):
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def validate_and_compress_image(filepath, max_size_mb=10, output_path=None):
    if not os.path.exists(filepath):
        return False
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if size_mb > max_size_mb:
        return False
    try:
        img = Image.open(filepath)
        img.verify()
    except Exception:
        return False
    if output_path and output_path != filepath:
        try:
            img = Image.open(filepath)
            img.save(output_path, optimize=True, quality=85)
        except Exception:
            return False
    return True


def extract_exif_metadata(image_path):
    return _parse_exif(image_path)
