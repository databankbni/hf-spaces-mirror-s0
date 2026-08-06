import os
import cv2
import csv
import math
import argparse
import random
import numpy as np
from collections import deque
from dataclasses import dataclass
from typing import Optional

# ============================================================
# 基础工具
# ============================================================

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def format_time(sec):
    if sec is None:
        return "n/a"
    m = int(sec // 60)
    s = sec - 60 * m
    return f"{m:02d}:{s:06.3f}"

def save_frame_at_time(video_path, t, output_path):
    if t is None:
        return None
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idx = int(round(t * fps))
    idx = max(0, min(total - 1, idx))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    cap.release()
    if ok:
        cv2.imwrite(output_path, frame)
        return output_path
    return None

def smooth_1d(x, win=9):
    x = np.asarray(x, dtype=np.float32)
    if len(x) == 0 or win <= 1:
        return x
    win = int(win)
    if win % 2 == 0:
        win += 1
    pad = win // 2
    xp = np.pad(x, (pad, pad), mode="edge")
    kernel = np.ones(win, dtype=np.float32) / float(win)
    return np.convolve(xp, kernel, mode="valid")

def angle_diff_deg(a, b):
    d = a - b
    while d > 180:
        d -= 360
    while d < -180:
        d += 360
    return d

def draw_text(img, text, org, scale=0.65, color=(255,255,255), thickness=2):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)

# ============================================================
# 配置类
# ============================================================

@dataclass
class VideoConfig:
    work_width: int = 1280
    sample_every: int = 2
    diff_lag_sec: float = 0.5

@dataclass
class MotionConfig:
    diff_thresh: int = 5
    blur_ksize: int = 5
    morph_open: int = 1
    morph_dilate: int = 1
    density_kernel: int = 9
    density_thresh: int = 3
    min_component_area: int = 12
    jitter_motion_ratio: float = 0.018
    jitter_component_count: int = 280
    jitter_median_area: float = 14
    jitter_spread_ratio: float = 0.45
    temporal_window: int = 24
    temporal_min_votes: int = 12
    temporal_dilate: int = 2
    temporal_mode: str = "intersection"
    orb_features: int = 1000

@dataclass
class PolarConfig:
    angle_min: float = -110.0
    angle_max: float = 70.0
    angle_bin: float = 2.0
    r_min: int = 80
    r_max: int = 1400
    r_bin: int = 20
    min_pixels_per_rbin: int = 2
    continuity_weight: float = 0.25
    max_angle_jump: float = 35.0
    smooth_win: int = 11
    score_threshold: Optional[float] = None
    threshold_k: float = 2.5
    min_move_sec: float = 4.0
    merge_gap_sec: float = 6.0
    ignore_start_sec: float = 0.0
    pre_lift_sec: float = 3.0
    post_place_sec: float = 1.5

@dataclass
class PcaConfig:
    pca_min_component_area: int = 80
    pca_min_length: float = 160
    pca_min_elongation: float = 4.0
    pca_max_width: float = 80
    pca_top_k: int = 1
    cluster_window: int = 7
    cluster_min_points: int = 5
    cluster_close_iter: int = 2
    cluster_dilate_iter: int = 2
    cluster_assign_dilate_iter: int = 2
    ransac_iterations: int = 2500
    line_dist_thresh: float = 18.0
    min_line_inliers: int = 8
    max_lines: int = 120
    save_debug_video: bool = True

# ============================================================
# ORB 仿射防抖
# ============================================================

def estimate_affine_orb(prev_gray, curr_gray, orb, good_match_ratio=0.22):
    identity = np.array([[1,0,0],[0,1,0]], dtype=np.float32)
    kp1, des1 = orb.detectAndCompute(prev_gray, None)
    kp2, des2 = orb.detectAndCompute(curr_gray, None)
    if des1 is None or des2 is None or len(kp1)<20 or len(kp2)<20:
        return identity, 0, 0, 0.0, 1.0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    if len(matches)<20:
        return identity, len(matches), 0, 0.0, 1.0
    matches = sorted(matches, key=lambda m:m.distance)
    keep_n = max(20, int(len(matches)*good_match_ratio))
    matches = matches[:keep_n]
    pts1 = np.float32([kp1[m.queryIdx].pt for m in matches])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in matches])
    M, inliers = cv2.estimateAffinePartial2D(pts1, pts2, method=cv2.RANSAC,
                ransacReprojThreshold=3.0, maxIters=2000, confidence=0.99, refineIters=10)
    if M is None:
        return identity, len(matches), 0, 0.0, 1.0
    inlier_count = int(inliers.sum()) if inliers is not None else 0
    a,b,tx = M[0]; c,d,ty = M[1]
    scale = math.sqrt(a*a + c*c)
    rot = math.degrees(math.atan2(c,a))
    if abs(tx)>45 or abs(ty)>45 or scale<0.94 or scale>1.06 or abs(rot)>4.0:
        return identity, len(matches), inlier_count, rot, scale
    return M.astype(np.float32), len(matches), inlier_count, rot, scale

def warp_affine_gray(gray, M):
    h,w = gray.shape[:2]
    return cv2.warpAffine(gray, M, (w,h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

# ============================================================
# 错误热点抑制
# ============================================================

def remove_small_components(mask, min_area=12):
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        return mask, 0, 0.0
    out = np.zeros_like(mask)
    areas = []
    for lab in range(1, num_labels):
        area = int(stats[lab, cv2.CC_STAT_AREA])
        areas.append(area)
        if area >= min_area:
            out[labels==lab] = 1
    median_area = float(np.median(areas)) if areas else 0.0
    comp_count = len(areas)
    return out, comp_count, median_area

def local_density_filter(mask, kernel_size=7, density_thresh=5):
    if kernel_size <= 1:
        return mask
    m = mask.astype(np.uint8)
    density = cv2.boxFilter(m, ddepth=cv2.CV_32F, ksize=(kernel_size,kernel_size), normalize=False)
    out = ((m>0) & (density>=density_thresh)).astype(np.uint8)
    return out

def grid_spread_ratio(mask, grid_x=16, grid_y=9):
    H,W = mask.shape[:2]
    active=0; total=grid_x*grid_y
    for gy in range(grid_y):
        y1 = int(round(gy*H/grid_y)); y2 = int(round((gy+1)*H/grid_y))
        for gx in range(grid_x):
            x1 = int(round(gx*W/grid_x)); x2 = int(round((gx+1)*W/grid_x))
            cell = mask[y1:y2, x1:x2]
            if cell.sum()>0:
                active+=1
    return active/float(total)

def suppress_global_jitter(mask, motion_ratio, comp_count, median_area, spread_ratio,
                           jitter_motion_ratio=0.018, jitter_component_count=280,
                           jitter_median_area=14, jitter_spread_ratio=0.45):
    is_jitter = (motion_ratio >= jitter_motion_ratio and comp_count >= jitter_component_count and
                 median_area <= jitter_median_area and spread_ratio >= jitter_spread_ratio)
    if not is_jitter:
        return mask, False
    filtered, _, _ = remove_small_components(mask, min_area=80)
    return filtered, True

def build_motion_mask(gray, lag_gray, orb, diff_thresh=8, blur_ksize=5, morph_open=1, morph_dilate=1,
                      density_kernel=7, density_thresh=5, min_component_area=12,
                      jitter_motion_ratio=0.018, jitter_component_count=280,
                      jitter_median_area=14, jitter_spread_ratio=0.45):
    if blur_ksize and blur_ksize>1:
        if blur_ksize%2==0: blur_ksize+=1
        gray_blur = cv2.GaussianBlur(gray, (blur_ksize,blur_ksize), 0)
        lag_blur = cv2.GaussianBlur(lag_gray, (blur_ksize,blur_ksize), 0)
    else:
        gray_blur = gray; lag_blur = lag_gray
    raw_diff = cv2.absdiff(gray_blur, lag_blur)
    raw_mask = (raw_diff>diff_thresh).astype(np.uint8)
    M, match_count, inlier_count, rot, scale = estimate_affine_orb(lag_blur, gray_blur, orb)
    lag_aligned = warp_affine_gray(lag_blur, M)
    stab_diff = cv2.absdiff(gray_blur, lag_aligned)
    stab_mask = (stab_diff>diff_thresh).astype(np.uint8)
    raw_motion_ratio = float(raw_mask.mean())
    stab_motion_ratio = float(stab_mask.mean())
    if morph_open>0:
        k = np.ones((3,3), np.uint8)
        stab_mask = cv2.morphologyEx(stab_mask, cv2.MORPH_OPEN, k, iterations=morph_open)
    density_mask = local_density_filter(stab_mask, kernel_size=density_kernel, density_thresh=density_thresh)
    component_mask, comp_count, median_area = remove_small_components(density_mask, min_area=min_component_area)
    spread = grid_spread_ratio(component_mask)
    final_mask, is_jitter = suppress_global_jitter(component_mask,
                motion_ratio=float(component_mask.mean()), comp_count=comp_count,
                median_area=median_area, spread_ratio=spread,
                jitter_motion_ratio=jitter_motion_ratio,
                jitter_component_count=jitter_component_count,
                jitter_median_area=jitter_median_area,
                jitter_spread_ratio=jitter_spread_ratio)
    if morph_dilate>0:
        k = np.ones((3,3), np.uint8)
        final_mask = cv2.dilate(final_mask, k, iterations=morph_dilate)
    info = {
        "M": M, "dx": float(M[0,2]), "dy": float(M[1,2]), "rot": float(rot),
        "scale": float(scale), "match_count": int(match_count), "inlier_count": int(inlier_count),
        "raw_motion_ratio": raw_motion_ratio, "stab_motion_ratio": stab_motion_ratio,
        "final_motion_ratio": float(final_mask.mean()), "component_count": int(comp_count),
        "median_area": float(median_area), "spread_ratio": float(spread), "is_jitter": bool(is_jitter)
    }
    debug = {
        "raw_mask": raw_mask, "stab_mask": stab_mask, "density_mask": density_mask,
        "component_mask": component_mask, "final_mask": final_mask,
        "raw_diff": raw_diff, "stab_diff": stab_diff
    }
    return final_mask, info, debug

# ============================================================
# 时序运动滤波器
# ============================================================

class TemporalMotionFilter:
    def __init__(self, window=30, min_votes=6, dilate_iter=2, mode="intersection"):
        self.window = int(window); self.min_votes = int(min_votes)
        self.dilate_iter = int(dilate_iter); self.mode = mode
        self.buffer = deque(maxlen=self.window)
        self.last_persistent = None
        self.last_vote_sum = None

    def update(self, mask):
        mask = (mask>0).astype(np.uint8)
        vote_mask = mask.copy()
        if self.dilate_iter>0:
            k = np.ones((3,3), np.uint8)
            vote_mask = cv2.dilate(vote_mask, k, iterations=self.dilate_iter)
        self.buffer.append(vote_mask)
        if len(self.buffer) < max(2, min(self.min_votes, self.window)):
            self.last_persistent = mask.copy()
            self.last_vote_sum = mask.astype(np.uint16)
            return mask
        vote_sum = np.zeros_like(mask, dtype=np.uint16)
        for m in self.buffer:
            vote_sum += m.astype(np.uint16)
        persistent = (vote_sum >= self.min_votes).astype(np.uint8)
        self.last_persistent = persistent.copy()
        self.last_vote_sum = vote_sum.copy()
        if self.mode == "vote":
            out = persistent
        else:
            out = ((mask>0) & (persistent>0)).astype(np.uint8)
        return out

# ============================================================
# 视频帧迭代器
# ============================================================

def iter_video_frames(video_path, video_cfg: VideoConfig):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H0 = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    scale = video_cfg.work_width / float(W0)
    work_height = int(round(H0 * scale))
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % video_cfg.sample_every == 0:
            t = frame_idx / fps
            small = cv2.resize(frame, (video_cfg.work_width, work_height), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            yield frame_idx, t, small, gray, fps, W0, H0, total_frames, scale, work_height
        frame_idx += 1
    cap.release()

# ============================================================
# 运动分析器（封装 ORB + 时序滤波）
# ============================================================

class MotionAnalyzer:
    def __init__(self, motion_cfg: MotionConfig, work_height: int, work_width: int):
        self.cfg = motion_cfg
        self.work_shape = (work_height, work_width)
        self.orb = cv2.ORB_create(nfeatures=motion_cfg.orb_features, scaleFactor=1.2, nlevels=8,
                                  edgeThreshold=31, patchSize=31)
        self.temporal_filter = TemporalMotionFilter(window=motion_cfg.temporal_window,
                                                    min_votes=motion_cfg.temporal_min_votes,
                                                    dilate_iter=motion_cfg.temporal_dilate,
                                                    mode=motion_cfg.temporal_mode)
        self.lag_samples = None
        self.gray_buffer = deque(maxlen=100)

    def set_lag_samples(self, lag_samples):
        self.lag_samples = lag_samples
        self.gray_buffer = deque(maxlen=lag_samples + 1)

    def process(self, gray):
        self.gray_buffer.append(gray)
        if self.lag_samples is None or len(self.gray_buffer) <= self.lag_samples:
            mask = np.zeros(self.work_shape, dtype=np.uint8)
            info = {
                "dx":0.0,"dy":0.0,"rot":0.0,"scale":1.0,"match_count":0,"inlier_count":0,
                "raw_motion_ratio":0.0,"stab_motion_ratio":0.0,"spatial_motion_ratio":0.0,
                "temporal_motion_ratio":0.0,"final_motion_ratio":0.0,
                "component_count":0,"median_area":0.0,"spread_ratio":0.0,"is_jitter":False
            }
            debug = {"raw_mask":mask.copy(), "stab_mask":mask.copy(), "density_mask":mask.copy(),
                     "component_mask":mask.copy(), "final_mask":mask.copy(),
                     "raw_diff":np.zeros(self.work_shape,dtype=np.uint8),
                     "stab_diff":np.zeros(self.work_shape,dtype=np.uint8)}
            return mask, info, debug

        lag_gray = self.gray_buffer[0]
        spatial_mask, info, debug = build_motion_mask(
            gray=gray, lag_gray=lag_gray, orb=self.orb,
            diff_thresh=self.cfg.diff_thresh,
            blur_ksize=self.cfg.blur_ksize,
            morph_open=self.cfg.morph_open,
            morph_dilate=self.cfg.morph_dilate,
            density_kernel=self.cfg.density_kernel,
            density_thresh=self.cfg.density_thresh,
            min_component_area=self.cfg.min_component_area,
            jitter_motion_ratio=self.cfg.jitter_motion_ratio,
            jitter_component_count=self.cfg.jitter_component_count,
            jitter_median_area=self.cfg.jitter_median_area,
            jitter_spread_ratio=self.cfg.jitter_spread_ratio
        )
        final_mask = self.temporal_filter.update(spatial_mask)
        info["spatial_motion_ratio"] = float(spatial_mask.mean())
        info["temporal_motion_ratio"] = float(self.temporal_filter.last_persistent.mean()) if self.temporal_filter.last_persistent is not None else 0.0
        info["final_motion_ratio"] = float(final_mask.mean())
        debug["temporal_display"] = self.temporal_filter.last_persistent if self.temporal_filter.last_persistent is not None else final_mask
        return final_mask, info, debug

# ============================================================
# 布尔序列处理（清洗短片段 + 合并间隙）
# ============================================================

def process_boolean_sequence(mask, min_len=1, max_gap=0):
    mask = np.asarray(mask, dtype=bool).copy()
    n = len(mask)
    # 清洗短片段
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if j - i < min_len:
            mask[i:j] = False
        i = j
    # 提取片段
    segs = []
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        segs.append((i, j-1))
        i = j
    if not segs:
        return mask
    # 合并
    merged = []
    cs, ce = segs[0]
    for s, e in segs[1:]:
        if s <= ce + max_gap + 1:
            ce = max(ce, e)
        else:
            merged.append((cs, ce))
            cs, ce = s, e
    merged.append((cs, ce))
    new_mask = np.zeros(n, dtype=bool)
    for s, e in merged:
        new_mask[s:e+1] = True
    return new_mask

# ============================================================
# PCA 线提取（用于自动估计旋转中心）
# ============================================================

def sliding_window_density_clusters(
        point_mask,
        window_size=80,
        min_points=10,
        close_iter=2,
        dilate_iter=2,
        assign_dilate_iter=2,
        min_cluster_points=30
):
    mask = (point_mask > 0).astype(np.uint8)
    if mask.sum() == 0:
        return [], np.zeros_like(mask), np.zeros_like(mask, dtype=np.int32)
    if window_size % 2 == 0:
        window_size += 1
    density = cv2.boxFilter(mask, ddepth=cv2.CV_32F, ksize=(window_size,window_size), normalize=False)
    dense_region = (density >= float(min_points)).astype(np.uint8)
    kernel = np.ones((3,3), np.uint8)
    if close_iter > 0:
        dense_region = cv2.morphologyEx(dense_region, cv2.MORPH_CLOSE, kernel, iterations=close_iter)
    if dilate_iter > 0:
        dense_region = cv2.dilate(dense_region, kernel, iterations=dilate_iter)
    num_labels, label_img, stats, _ = cv2.connectedComponentsWithStats(dense_region, connectivity=8)
    clusters = []
    for lab in range(1, num_labels):
        x = int(stats[lab, cv2.CC_STAT_LEFT])
        y = int(stats[lab, cv2.CC_STAT_TOP])
        w = int(stats[lab, cv2.CC_STAT_WIDTH])
        h = int(stats[lab, cv2.CC_STAT_HEIGHT])
        dense_area = int(stats[lab, cv2.CC_STAT_AREA])
        cluster_mask = (label_img == lab).astype(np.uint8)
        if assign_dilate_iter > 0:
            cluster_assign = cv2.dilate(cluster_mask, kernel, iterations=assign_dilate_iter)
        else:
            cluster_assign = cluster_mask
        ys, xs = np.where((mask > 0) & (cluster_assign > 0))
        if xs.size < min_cluster_points:
            continue
        points = np.stack([xs, ys], axis=1).astype(np.float32)
        clusters.append({
            "label": lab,
            "points": points,
            "bbox": (x, y, w, h),
            "dense_area": dense_area,
            "point_count": int(xs.size)
        })
    return clusters, dense_region, label_img

def pca_line_from_points(points):
    pts = np.asarray(points, dtype=np.float32)
    if pts.shape[0] < 5:
        return None
    center = pts.mean(axis=0)
    X = pts - center
    cov = np.cov(X.T)
    if cov.shape != (2,2):
        return None
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    direction = eigvecs[:, 0].astype(np.float32)
    direction = direction / (np.linalg.norm(direction) + 1e-6)
    normal = np.array([-direction[1], direction[0]], dtype=np.float32)
    proj_main = X @ direction
    proj_side = X @ normal
    length = float(np.percentile(proj_main, 98) - np.percentile(proj_main, 2))
    width = float(np.percentile(proj_side, 98) - np.percentile(proj_side, 2))
    elongation = length / max(width, 1e-6)
    return {
        "center": center.astype(np.float32),
        "direction": direction.astype(np.float32),
        "normal": normal.astype(np.float32),
        "length": length,
        "width": width,
        "elongation": elongation,
        "area": int(len(points))
    }

def line_to_normal_form(center, direction):
    d = direction.astype(np.float32)
    d = d / (np.linalg.norm(d) + 1e-6)
    n = np.array([-d[1], d[0]], dtype=np.float32)
    n = n / (np.linalg.norm(n) + 1e-6)
    b = float(n @ center)
    return n, b

def intersect_two_lines(line1, line2):
    n1, b1 = line1
    n2, b2 = line2
    A = np.stack([n1, n2], axis=0).astype(np.float32)
    b = np.array([b1, b2], dtype=np.float32)
    det = float(np.linalg.det(A))
    if abs(det) < 1e-6:
        return None
    try:
        p = np.linalg.solve(A, b)
        return p.astype(np.float32)
    except Exception:
        return None

def point_line_distance(point, line):
    n, b = line
    return abs(float(n @ point - b))

def estimate_pivot_from_lines_ransac(
        lines,
        width,
        height,
        iterations=2000,
        dist_thresh=18.0,
        min_inliers=8,
        seed=123
):
    if len(lines) < 3:
        return None, None
    rng = random.Random(seed)
    best_point = None
    best_inliers = None
    best_score = -1e18
    x_min, x_max = -0.2 * width, 1.2 * width
    y_min, y_max = -0.2 * height, 1.2 * height
    n_lines = len(lines)
    for _ in range(iterations):
        i, j = rng.sample(range(n_lines), 2)
        p = intersect_two_lines(lines[i]["line"], lines[j]["line"])
        if p is None:
            continue
        x, y = float(p[0]), float(p[1])
        if not (x_min <= x <= x_max and y_min <= y <= y_max):
            continue
        dists = np.array([point_line_distance(p, ln["line"]) for ln in lines], dtype=np.float32)
        inliers = dists < dist_thresh
        cnt = int(inliers.sum())
        if cnt < min_inliers:
            continue
        mean_dist = float(dists[inliers].mean())
        score = cnt * 10.0 - mean_dist * 1.5
        if y > 0.75 * height:
            score -= 200.0
        if score > best_score:
            best_score = score
            best_point = p
            best_inliers = inliers
    if best_point is None:
        return None, None
    A = []
    b = []
    weights = []
    for keep, ln in zip(best_inliers, lines):
        if not keep:
            continue
        n, bb = ln["line"]
        A.append(n)
        b.append(bb)
        w = max(1.0, ln["length"] * min(ln["elongation"], 12.0) / 100.0)
        weights.append(w)
    A = np.asarray(A, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    weights = np.asarray(weights, dtype=np.float32)
    try:
        W = np.diag(weights)
        AtW = A.T @ W
        p_refined = np.linalg.solve(AtW @ A, AtW @ b)
        best_point = p_refined.astype(np.float32)
    except Exception:
        pass
    final_dists = np.array([point_line_distance(best_point, ln["line"]) for ln in lines], dtype=np.float32)
    final_inliers = final_dists < dist_thresh
    info = {
        "line_count": int(len(lines)),
        "inlier_count": int(final_inliers.sum()),
        "mean_dist": float(final_dists[final_inliers].mean()) if final_inliers.any() else None,
        "median_dist": float(np.median(final_dists[final_inliers])) if final_inliers.any() else None,
        "score": float(best_score)
    }
    return best_point, info

def extract_boom_like_component_lines(
        mask,
        min_component_area=80,
        min_pca_length=160,
        min_elongation=4.0,
        max_width=80,
        top_k=1,
        cluster_window=90,
        cluster_min_points=10,
        cluster_close_iter=2,
        cluster_dilate_iter=2,
        cluster_assign_dilate_iter=2
):
    clusters, dense_region, label_img = sliding_window_density_clusters(
        point_mask=mask,
        window_size=cluster_window,
        min_points=cluster_min_points,
        close_iter=cluster_close_iter,
        dilate_iter=cluster_dilate_iter,
        assign_dilate_iter=cluster_assign_dilate_iter,
        min_cluster_points=min_component_area
    )
    candidates = []
    for cl in clusters:
        pts = cl["points"]
        area = int(cl["point_count"])
        if area < min_component_area:
            continue
        line_info = pca_line_from_points(pts)
        if line_info is None:
            continue
        length = line_info["length"]
        width = line_info["width"]
        elongation = line_info["elongation"]
        if length < min_pca_length:
            continue
        if elongation < min_elongation:
            continue
        if width > max_width:
            continue
        score = length * min(elongation, 15.0) * math.log1p(area)
        n, b = line_to_normal_form(line_info["center"], line_info["direction"])
        line_info["line"] = (n, b)
        line_info["label"] = int(cl["label"])
        line_info["score"] = float(score)
        line_info["cluster_bbox"] = cl["bbox"]
        line_info["dense_area"] = cl["dense_area"]
        line_info["area"] = area
        candidates.append(line_info)
    candidates.sort(key=lambda z: z["score"], reverse=True)
    return candidates[:top_k], dense_region

def draw_pca_line(vis, line_info, color=(0,255,255), thickness=2):
    if line_info is None:
        return
    center = line_info["center"]
    direction = line_info["direction"]
    length = line_info["length"]
    p1 = center - direction * length * 0.55
    p2 = center + direction * length * 0.55
    cv2.line(vis, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), color, thickness, cv2.LINE_AA)
    cv2.circle(vis, (int(center[0]), int(center[1])), 4, color, -1)

# ============================================================
# 极坐标评分
# ============================================================

def longest_consecutive_run(sorted_indices):
    if len(sorted_indices) == 0:
        return 0
    sorted_indices = sorted(sorted_indices)
    best = 1
    cur = 1
    for i in range(1, len(sorted_indices)):
        if sorted_indices[i] == sorted_indices[i-1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best

def compute_polar_motion_scores(
        motion_mask,
        pivot,
        angle_centers,
        angle_bin,
        r_min,
        r_max,
        r_bin,
        min_pixels_per_rbin
):
    px, py = pivot
    ys, xs = np.where(motion_mask > 0)
    n_angles = len(angle_centers)
    scores = np.zeros(n_angles, dtype=np.float32)
    coverages = np.zeros(n_angles, dtype=np.float32)
    runs = np.zeros(n_angles, dtype=np.float32)
    counts = np.zeros(n_angles, dtype=np.float32)
    n_r_bins = max(1, int(math.ceil((r_max - r_min) / float(r_bin))))
    if xs.size == 0:
        return scores, coverages, runs, counts
    dx = xs.astype(np.float32) - float(px)
    dy = ys.astype(np.float32) - float(py)
    r = np.sqrt(dx*dx + dy*dy)
    theta = np.degrees(np.arctan2(dy, dx))
    valid = (r >= r_min) & (r <= r_max)
    if valid.sum() == 0:
        return scores, coverages, runs, counts
    r = r[valid]
    theta = theta[valid]
    for i, ac in enumerate(angle_centers):
        lo = ac - angle_bin/2.0
        hi = ac + angle_bin/2.0
        am = (theta >= lo) & (theta < hi)
        if am.sum() == 0:
            continue
        rr = r[am]
        r_indices = np.floor((rr - r_min) / float(r_bin)).astype(np.int32)
        r_indices = np.clip(r_indices, 0, n_r_bins - 1)
        hist = np.bincount(r_indices, minlength=n_r_bins)
        covered = np.where(hist >= min_pixels_per_rbin)[0]
        if len(covered) == 0:
            continue
        coverage_ratio = len(covered) / float(n_r_bins)
        run_ratio = longest_consecutive_run(covered) / float(n_r_bins)
        count = float(am.sum())
        count_factor = math.log1p(count) / 10.0
        count_factor = min(1.0, count_factor)
        score = 0.55 * coverage_ratio + 0.35 * run_ratio + 0.10 * count_factor
        scores[i] = float(score)
        coverages[i] = float(coverage_ratio)
        runs[i] = float(run_ratio)
        counts[i] = float(count)
    return scores, coverages, runs, counts

def select_angle_with_continuity(
        raw_scores,
        angle_centers,
        prev_angle,
        continuity_weight=0.25,
        max_angle_jump=35.0
):
    if raw_scores.size == 0:
        return 0, 0.0, 1.0
    scores = raw_scores.copy()
    mean_score = float(np.mean(scores)) + 1e-9
    max_score = float(np.max(scores)) + 1e-9
    peakiness = max_score / mean_score
    if prev_angle is not None:
        for i, ang in enumerate(angle_centers):
            da = abs(angle_diff_deg(float(ang), float(prev_angle)))
            scores[i] -= continuity_weight * (da / max(max_angle_jump, 1e-6)) ** 2
            if da > max_angle_jump:
                scores[i] -= 0.30
    best_idx = int(np.argmax(scores))
    best_score = float(raw_scores[best_idx])
    peak_factor = min(1.0, max(0.0, (peakiness - 1.0) / 2.0))
    best_score *= peak_factor
    return best_idx, best_score, float(peakiness)

# ============================================================
# 可视化工具
# ============================================================

def overlay_mask_bgr(frame_bgr, mask, color=(0,0,255), alpha=0.75):
    out = frame_bgr.copy()
    if mask is None:
        return out
    m = mask.astype(bool)
    if m.any():
        out[m] = (out[m].astype(np.float32) * (1 - alpha) + np.array(color, dtype=np.float32) * alpha).astype(np.uint8)
    return out

def draw_pivot_and_ray(vis, pivot, angle_deg, r_min, r_max, color=(0,255,255)):
    px, py = pivot
    theta = math.radians(float(angle_deg))
    x1 = int(px + r_min * math.cos(theta))
    y1 = int(py + r_min * math.sin(theta))
    x2 = int(px + r_max * math.cos(theta))
    y2 = int(py + r_max * math.sin(theta))
    cv2.circle(vis, (int(px), int(py)), 7, (0,0,255), -1)
    cv2.line(vis, (x1, y1), (x2, y2), color, 3, cv2.LINE_AA)

def make_four_panel_debug(frame, raw_mask, temporal_mask, density_mask, final_mask, text):
    H, W = frame.shape[:2]
    panel_w = W // 2
    panel_h = H // 2
    def panel(mask, title):
        vis = cv2.resize(frame, (panel_w, panel_h), interpolation=cv2.INTER_AREA)
        m = cv2.resize(mask.astype(np.uint8), (panel_w, panel_h), interpolation=cv2.INTER_NEAREST)
        vis = overlay_mask_bgr(vis, m, color=(0,0,255), alpha=0.75)
        cv2.putText(vis, title, (12,28), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255,255,255), 2, cv2.LINE_AA)
        return vis
    p1 = panel(raw_mask, "1 RAW DIFF")
    p2 = panel(temporal_mask, "2 TEMPORAL FILTERED")
    p3 = panel(density_mask, "3 DENSITY FILTERED")
    p4 = panel(final_mask, "4 FINAL MOTION MASK")
    top = np.hstack([p1, p2])
    bottom = np.hstack([p3, p4])
    out = np.vstack([top, bottom])
    cv2.putText(out, text, (20, out.shape[0]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0,255,255), 2, cv2.LINE_AA)
    return out

# ============================================================
# 精简后的自动估计旋转中心（无文件输出）
# ============================================================

def auto_pivot_no_output(video_path, video_cfg: VideoConfig, motion_cfg: MotionConfig, pca_cfg: PcaConfig):
    """只返回 (pivot_x_original, pivot_y_original)，不保存任何文件"""
    for _, _, _, _, fps, W0, H0, total_frames, scale, work_height in iter_video_frames(video_path, video_cfg):
        break
    work_width = video_cfg.work_width

    sample_dt = video_cfg.sample_every / fps
    lag_samples = max(1, int(round(video_cfg.diff_lag_sec / max(sample_dt, 1e-9))))

    analyzer = MotionAnalyzer(motion_cfg, work_height, work_width)
    analyzer.set_lag_samples(lag_samples)

    pca_lines = []
    for frame_idx, t, small, gray, _, _, _, _, _, _ in iter_video_frames(video_path, video_cfg):
        final_mask, info, debug = analyzer.process(gray)
        selected_lines, _ = extract_boom_like_component_lines(
            final_mask,
            min_component_area=pca_cfg.pca_min_component_area,
            min_pca_length=pca_cfg.pca_min_length,
            min_elongation=pca_cfg.pca_min_elongation,
            max_width=pca_cfg.pca_max_width,
            top_k=pca_cfg.pca_top_k,
            cluster_window=pca_cfg.cluster_window,
            cluster_min_points=pca_cfg.cluster_min_points,
            cluster_close_iter=pca_cfg.cluster_close_iter,
            cluster_dilate_iter=pca_cfg.cluster_dilate_iter,
            cluster_assign_dilate_iter=pca_cfg.cluster_assign_dilate_iter
        )
        for ln in selected_lines:
            pca_lines.append({
                "frame": frame_idx, "time": t,
                "center": ln["center"], "direction": ln["direction"],
                "normal": ln["normal"], "line": ln["line"],
                "length": ln["length"], "width": ln["width"],
                "elongation": ln["elongation"], "area": ln["area"], "score": ln["score"]
            })
        if len(pca_lines) > pca_cfg.max_lines:
            pca_lines.sort(key=lambda z: z["score"], reverse=True)
            pca_lines = pca_lines[:pca_cfg.max_lines]

    if len(pca_lines) < 3:
        raise RuntimeError(f"有效 PCA 线太少：{len(pca_lines)}，无法估计旋转中心。")

    center, ransac_info = estimate_pivot_from_lines_ransac(
        pca_lines, width=work_width, height=work_height,
        iterations=pca_cfg.ransac_iterations,
        dist_thresh=pca_cfg.line_dist_thresh,
        min_inliers=pca_cfg.min_line_inliers
    )
    if center is None:
        raise RuntimeError("PCA 线交点 RANSAC 估计旋转点失败。")

    cx_work, cy_work = float(center[0]), float(center[1])
    cx_orig = cx_work / scale
    cy_orig = cy_work / scale
    return cx_orig, cy_orig


# ============================================================
# 精简后的极坐标运动检测（无文件输出）
# ============================================================

def detect_polar_motion_no_output(
        video_path,
        pivot_x,
        pivot_y,
        video_cfg: VideoConfig,
        motion_cfg: MotionConfig,
        polar_cfg: PolarConfig
):
    """只返回 (boom_start, boom_end, lift_start, place_end)"""
    # 获取视频元数据
    for _, _, _, _, fps, W0, H0, total_frames, scale, work_height in iter_video_frames(video_path, video_cfg):
        break
    work_width = video_cfg.work_width
    duration = total_frames / fps if fps > 0 else 0.0

    pivot = (float(pivot_x) * scale, float(pivot_y) * scale)
    sample_dt = video_cfg.sample_every / fps
    lag_samples = max(1, int(round(video_cfg.diff_lag_sec / max(sample_dt, 1e-9))))
    angle_centers = np.arange(polar_cfg.angle_min, polar_cfg.angle_max + 1e-6, polar_cfg.angle_bin, dtype=np.float32)

    analyzer = MotionAnalyzer(motion_cfg, work_height, work_width)
    analyzer.set_lag_samples(lag_samples)

    rows = []
    energy_matrix = []
    prev_angle = None

    for frame_idx, t, small, gray, _, _, _, _, _, _ in iter_video_frames(video_path, video_cfg):
        final_mask, info, debug = analyzer.process(gray)

        if final_mask.sum() == 0:
            scores = np.zeros(len(angle_centers), dtype=np.float32)
            best_angle = float(angle_centers[0])
            best_score = 0.0
            peakiness = 1.0
        else:
            scores, _, _, _ = compute_polar_motion_scores(
                motion_mask=final_mask,
                pivot=pivot,
                angle_centers=angle_centers,
                angle_bin=polar_cfg.angle_bin,
                r_min=polar_cfg.r_min,
                r_max=polar_cfg.r_max,
                r_bin=polar_cfg.r_bin,
                min_pixels_per_rbin=polar_cfg.min_pixels_per_rbin
            )
            best_idx, best_score, peakiness = select_angle_with_continuity(
                raw_scores=scores,
                angle_centers=angle_centers,
                prev_angle=prev_angle,
                continuity_weight=polar_cfg.continuity_weight,
                max_angle_jump=polar_cfg.max_angle_jump
            )
            best_angle = float(angle_centers[best_idx])
            prev_angle = best_angle

        energy_matrix.append(scores.copy())
        rows.append({
            "time": t,
            "score": best_score,
            "final_motion_ratio": info["final_motion_ratio"]
        })

    if len(rows) < 5:
        raise RuntimeError("采样点太少，无法分析")

    times = np.array([r["time"] for r in rows], dtype=np.float32)
    score = np.array([r["score"] for r in rows], dtype=np.float32)
    final_motion = np.array([r["final_motion_ratio"] for r in rows], dtype=np.float32)

    score_smooth = smooth_1d(score, win=polar_cfg.smooth_win)
    final_smooth = smooth_1d(final_motion, win=polar_cfg.smooth_win)

    valid = times >= polar_cfg.ignore_start_sec
    if valid.sum() < 5:
        valid[:] = True
    score_for_th = score_smooth[valid]
    if polar_cfg.score_threshold is None:
        med = float(np.median(score_for_th))
        mad = float(np.median(np.abs(score_for_th - med))) + 1e-9
        mean = float(np.mean(score_for_th))
        std = float(np.std(score_for_th))
        threshold = max(med + polar_cfg.threshold_k * mad, mean + 0.6 * std, 1e-7)
    else:
        threshold = float(polar_cfg.score_threshold)

    moving = score_smooth > threshold
    moving[times < polar_cfg.ignore_start_sec] = False

    sample_dt2 = float(np.median(np.diff(times))) if len(times) > 1 else video_cfg.sample_every / fps
    min_move_len = max(2, int(round(polar_cfg.min_move_sec / max(sample_dt2, 1e-6))))
    merge_gap_len = max(1, int(round(polar_cfg.merge_gap_sec / max(sample_dt2, 1e-6))))

    moving_clean = process_boolean_sequence(moving, min_len=min_move_len, max_gap=merge_gap_len)

    segs = []
    n = len(moving_clean)
    i = 0
    while i < n:
        if not moving_clean[i]:
            i += 1
            continue
        j = i
        while j < n and moving_clean[j]:
            j += 1
        segs.append((i, j - 1))
        i = j

    if not segs:
        # 降低阈值再试
        threshold2 = max(threshold * 0.45, 1e-8)
        moving2 = score_smooth > threshold2
        moving2[times < polar_cfg.ignore_start_sec] = False
        min_move_len2 = max(2, int(round((polar_cfg.min_move_sec * 0.5) / max(sample_dt2, 1e-6))))
        moving2 = process_boolean_sequence(moving2, min_len=min_move_len2, max_gap=merge_gap_len)
        segs = []
        i = 0
        while i < n:
            if not moving2[i]:
                i += 1
                continue
            j = i
            while j < n and moving2[j]:
                j += 1
            segs.append((i, j - 1))
            i = j

    if not segs:
        boom_start = boom_end = lift_start = place_end = None
    else:
        def seg_score(seg):
            s, e = seg
            dur = float(times[e] - times[s])
            score_sum = float(np.sum(score_smooth[s:e + 1]))
            score_max = float(np.max(score_smooth[s:e + 1]))
            final_motion_sum = float(np.sum(final_smooth[s:e + 1]))
            return score_sum * 12.0 + score_max * 4.0 + dur * 0.35 + final_motion_sum * 2.0
        selected_seg = max(segs, key=seg_score)
        s, e = selected_seg
        boom_start = float(times[s])
        boom_end = float(times[e])
        lift_start = max(0.0, boom_start - polar_cfg.pre_lift_sec)
        place_end = min(duration, boom_end + polar_cfg.post_place_sec)

    return boom_start, boom_end, lift_start, place_end


# ============================================================
# 统一入口：只需传入视频路径，可选提供 pivot
# ============================================================

def get_boom_times(video_path, pivot_x=None, pivot_y=None):
    """
    计算塔吊四个关键时间点。
    如果未提供 pivot_x, pivot_y，则自动估计。
    返回字典: {'boom_start', 'boom_end', 'lift_start', 'place_end'}
    """
    # 使用默认配置（可根据需要调整）
    video_cfg = VideoConfig()
    motion_cfg = MotionConfig()
    polar_cfg = PolarConfig()
    pca_cfg = PcaConfig()

    if pivot_x is None or pivot_y is None:
        pivot_x, pivot_y = auto_pivot_no_output(video_path, video_cfg, motion_cfg, pca_cfg)

    boom_start, boom_end, lift_start, place_end = detect_polar_motion_no_output(
        video_path, pivot_x, pivot_y, video_cfg, motion_cfg, polar_cfg
    )

    return {
        "boom_start": boom_start,
        "boom_end": boom_end,
        "lift_start": lift_start,
        "place_end": place_end
    }


# ============================================================
# 测试入口（直接运行打印结果）
# ============================================================

if __name__ == "__main__":
    import sys

    # 默认视频路径（请根据实际情况修改）
    DEFAULT_VIDEO = r"E:\CLIP model\Crane 2Dto3D\Crane_working_2.mp4"

    if len(sys.argv) < 2:
        print(f"未提供视频路径，使用默认视频: {DEFAULT_VIDEO}")
        video = DEFAULT_VIDEO
        px = py = None
    else:
        video = sys.argv[1]
        px = float(sys.argv[2]) if len(sys.argv) > 2 else None
        py = float(sys.argv[3]) if len(sys.argv) > 3 else None

    result = get_boom_times(video, px, py)
    print("\n================= RESULT =================")
    for key in ["boom_start", "boom_end", "lift_start", "place_end"]:
        val = result[key]
        if val is not None:
            print(f"{key:15s}: {val:.3f}s  ({format_time(val)})")
        else:
            print(f"{key:15s}: n/a")
    print("==========================================")