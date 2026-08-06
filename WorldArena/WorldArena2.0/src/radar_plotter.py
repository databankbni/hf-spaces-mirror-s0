import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from typing import Dict, List

class RadarPlotter:
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.dimension_metrics = list(data_loader.DIMENSION_MAP.keys())
        
        # 预定义颜色列表，确保足够多
        self.COLOR_LIST = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
        ]
        
        # 标记样式
        self.MARKER_STYLES = ['o', 's', '^', 'D', 'v', 'p', 'h', '*', 'X', 'P', 'd']
        # 线型样式
        self.LINE_STYLES = ['-', '--', '-.', ':']
        
        # 颜色缓存
        self.model_color_cache = {}
        self.model_style_cache = {}
        
    def create_radar_chart(self, models_df: pd.DataFrame) -> plt.Figure:
        """创建雷达图 - 展示维度指标"""
        if models_df.empty or len(models_df) == 0:
            fig, ax = plt.subplots(figsize=(8, 8))
            ax.text(0.5, 0.5, "No data available for radar chart", 
                    ha="center", va="center", fontsize=14)
            ax.axis("off")
            return fig
        
        # 获取维度指标
        labels = self.dimension_metrics
        # 设置中文字体
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['Arial', 'Microsoft YaHei', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建图形，左侧为雷达图，右侧留出图例空间
        fig, (ax, ax_legend) = plt.subplots(
            1, 2,
            figsize=(14, 8),
            gridspec_kw={'width_ratios': [3, 1]},
            subplot_kw={'polar': True}
        )
        
        # 绘制雷达图
        self._draw_radar(ax, models_df, labels)
        
        # 在右侧轴上创建图例
        ax_legend.axis('off')  # 关闭右侧轴的显示
        legend_elements = self._create_legend_elements(models_df)
        
        if legend_elements:
            ax_legend.legend(
                handles=legend_elements,
                loc='center',
                frameon=True,
                fontsize=10,
                fancybox=True,
                shadow=True,
                edgecolor='gray',
                facecolor='white'
            )
        
        plt.tight_layout()
        return fig
    
    def _draw_radar(self, ax, models_df: pd.DataFrame, labels: List[str]):
        """绘制雷达图（参考您提供的代码风格）"""
        N = len(labels)
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]
        
        # 设置雷达图基本参数
        DISPLAY_MAX = 105
        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_ylim(0, DISPLAY_MAX)
        
        # 隐藏默认的极坐标边框
        ax.spines["polar"].set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        
        # 网格刻度（参考您提供的代码）
        true_ticks = [0, 20, 40, 60, 80, 100]
        ax.set_yticks(true_ticks)
        ax.set_yticklabels([str(t) for t in true_ticks], fontsize=10, color="#666666")
        ax.yaxis.grid(True, color="#D0D8E8", linewidth=0.8, linestyle='-')
        
        # 蓝色背景填充（参考您提供的代码）
        ax.fill(np.linspace(0, 2*np.pi, 400), [DISPLAY_MAX]*400, color="#EAF1FA", alpha=0.6)
        
        # 径向参考线（参考您提供的代码）
        for angle in angles[:-1]:
            ax.plot([angle, angle], [0, DISPLAY_MAX], color="#D0D8E8", linewidth=0.8, zorder=1)
        
        # 外围灰色弧线作为标签背景（参考您提供的代码）
        outer_r = DISPLAY_MAX + 1.5
        arc_width = 2 * np.pi / N * 0.70
        for angle in angles[:-1]:
            theta = np.linspace(angle - arc_width/2, angle + arc_width/2, 80)
            ax.plot(theta, [outer_r]*len(theta), color="#C8C8C8", linewidth=6, solid_capstyle="round")
        
        # 标签位置映射（参考您提供的代码）
        label_r_map = {
            "Visual Quality": DISPLAY_MAX + 8,
            "Motion Quality": DISPLAY_MAX + 15,
            "Content Consistency": DISPLAY_MAX + 15,
            "Physics Adherence": DISPLAY_MAX + 8,
            "3D Accuracy": DISPLAY_MAX + 15,
            "Controllability": DISPLAY_MAX + 15,
        }
        
        # 绘制标签（支持换行，参考您提供的代码）
        for angle, label in zip(angles[:-1], labels):
            label_r = label_r_map.get(label, DISPLAY_MAX + 10)
            # 将长标签分两行显示
            display_label = label
            if label == "Content Consistency":
                display_label = "Content\nConsistency"
            elif label == "Physics Adherence":
                display_label = "Physics\nAdherence"
            elif label == "Visual Quality":
                display_label = "Visual\nQuality"
            elif label == "Motion Quality":
                display_label = "Motion\nQuality"
            elif label == "3D Accuracy":
                display_label = "3D\nAccuracy"
            elif label == "Controllability":
                display_label = "Controllability"
            
            ax.text(angle, label_r, display_label, ha="center", va="center",
                   fontsize=11, fontweight="bold", clip_on=False, color="#333333")
        
        # 为每个模型分配颜色和样式（如果尚未分配）
        all_models = models_df["Model"].values.tolist()
        for i, model in enumerate(all_models):
            if model not in self.model_color_cache:
                # 使用循环的颜色列表
                color_idx = i % len(self.COLOR_LIST)
                self.model_color_cache[model] = self.COLOR_LIST[color_idx]
            
            if model not in self.model_style_cache:
                # 分配线型和标记
                line_idx = i % len(self.LINE_STYLES)
                marker_idx = i % len(self.MARKER_STYLES)
                self.model_style_cache[model] = {
                    'linestyle': self.LINE_STYLES[line_idx],
                    'marker': self.MARKER_STYLES[marker_idx]
                }
        
        # 计算每个模型的平均分并排序（从低到高绘制，高分在上层）
        model_scores = {}
        for model in all_models:
            model_data = models_df[models_df["Model"] == model]
            score_sum = 0
            count = 0
            for dim in labels:
                if dim in model_data.columns:
                    val = model_data[dim].values[0]
                    if not pd.isna(val):
                        score_sum += float(val)
                        count += 1
            model_scores[model] = score_sum / count if count > 0 else 0
        
        # 按平均分排序（从低到高）
        sorted_models = sorted(model_scores.items(), key=lambda x: x[1])
        
        # 绘制每个模型的数据
        for idx, (model, _) in enumerate(sorted_models):
            model_data = models_df[models_df["Model"] == model]
            values = []
            
            # 收集每个维度的值
            for dim in labels:
                if dim in model_data.columns:
                    val = model_data[dim].values[0]
                    if pd.isna(val):
                        values.append(0)
                    else:
                        values.append(float(val))
                else:
                    values.append(0)
            
            # 闭合多边形
            values += values[:1]
            
            # 获取颜色和样式
            color = self.model_color_cache.get(model, "#333333")
            style = self.model_style_cache.get(model, {'linestyle': '-', 'marker': 'o'})
            
            # 绘制雷达图线（参考您提供的代码风格）
            ax.plot(angles, values, color=color, linewidth=2.0, 
                   linestyle=style['linestyle'], zorder=10 + idx)
            ax.scatter(angles[:-1], values[:-1], color=color, s=40, 
                      marker=style['marker'], zorder=20 + idx, edgecolors='white', linewidths=0.6)
            ax.fill(angles, values, color=color, alpha=0.05)
    
    def _create_legend_elements(self, models_df: pd.DataFrame):
        """创建图例元素（参考您提供的代码风格）"""
        legend_elements = []
        all_models = models_df["Model"].values.tolist()
        
        if not all_models:
            return legend_elements
        
        # 计算平均分并排序
        model_scores = {}
        for model in all_models:
            model_data = models_df[models_df["Model"] == model]
            score_sum = 0
            count = 0
            for dim in self.dimension_metrics:
                if dim in model_data.columns:
                    val = model_data[dim].values[0]
                    if not pd.isna(val):
                        score_sum += float(val)
                        count += 1
            model_scores[model] = score_sum / count if count > 0 else 0
        
        # 按平均分排序
        sorted_models = sorted(model_scores.items(), key=lambda x: x[1])
        
        for model, _ in sorted_models:
            color = self.model_color_cache.get(model, "#333333")
            style = self.model_style_cache.get(model, {'linestyle': '-', 'marker': 'o'})
            
            legend_elements.append(
                Line2D([0], [0], color=color, linestyle=style['linestyle'], 
                      marker=style['marker'], markersize=6, linewidth=2.0,
                      markerfacecolor=color, markeredgecolor='white', markeredgewidth=0.5,
                      label=model)
            )
        
        return legend_elements
    
    def get_dimension_scores(self, model_name: str) -> Dict[str, float]:
        """获取指定模型的维度分数"""
        if self.data_loader.df_all is None or model_name not in self.data_loader.df_all["Model"].values:
            return {}
        
        model_data = self.data_loader.df_all[self.data_loader.df_all["Model"] == model_name]
        scores = {}
        
        for dim in self.dimension_metrics:
            if dim in model_data.columns:
                scores[dim] = float(model_data[dim].values[0]) if not pd.isna(model_data[dim].values[0]) else 0.0
        
        return scores
