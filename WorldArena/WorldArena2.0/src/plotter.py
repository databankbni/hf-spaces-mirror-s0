import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from typing import Optional

class Plotter:
    def __init__(self, data_loader):
        self.data_loader = data_loader
    
    def create_comparison_plot(
        self,
        model_filter: str,
        open_source_filter: str,
        year_filter: str,
        selected_plot_metric: str,
        plot_sort_mode: str,
        display_metric_name: Optional[str] = None,
    ) -> plt.Figure:
        """创建对比图 - 单指标多模型对比"""

        metric_display_name = display_metric_name or selected_plot_metric
    
        df = self.data_loader.df_all
        
        if df is None or df.empty:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, "No data available for plotting",
                    ha="center", va="center", fontsize=14)
            ax.axis("off")
            return fig
        
        # 应用筛选条件
        if model_filter and model_filter.strip():
            df = df[df["Model"].str.contains(model_filter, case=False, na=False)]
        
        if open_source_filter and open_source_filter != "All":
            df = df[df["open_source"] == open_source_filter]
        
        if year_filter and year_filter != "All":
            df = df[df["year"] == year_filter]
        
        if df.empty:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, "No models match the filter criteria",
                    ha="center", va="center", fontsize=14)
            ax.axis("off")
            return fig
        
        if not selected_plot_metric:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, "Please select a metric",
                    ha="center", va="center", fontsize=14)
            ax.axis("off")
            return fig
        
        # 检查指标是否存在
        if selected_plot_metric not in df.columns:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, f"Metric '{selected_plot_metric}' not found",
                    ha="center", va="center", fontsize=14)
            ax.axis("off")
            return fig
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial', 'Microsoft YaHei', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 准备数据
        plot_df = df[["Model", selected_plot_metric]].copy()
        plot_df = plot_df.dropna(subset=[selected_plot_metric])
        
        if plot_df.empty:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, f"No data for metric '{metric_display_name}'",
                    ha="center", va="center", fontsize=14)
            ax.axis("off")
            return fig
        
        # 重命名列以便使用
        plot_df.columns = ['Model', 'Score']
        
        # 确保Score是数值类型
        plot_df['Score'] = pd.to_numeric(plot_df['Score'], errors='coerce')
        
        # 移除NaN值
        plot_df = plot_df.dropna(subset=['Score'])
        
        if plot_df.empty:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, f"No valid data for metric '{metric_display_name}'",
                    ha="center", va="center", fontsize=14)
            ax.axis("off")
            return fig
        
        # 保留2位小数
        plot_df['Score'] = plot_df['Score'].round(2)
        
        # 根据排序模式排序
        ascending = (plot_sort_mode != "Ascending (low → high)")
        ascending = plot_sort_mode.startswith("Descending")
        plot_df = plot_df.sort_values('Score', ascending=ascending)

        model_count = len(plot_df)
        figure_height = max(9, min(22, 0.5 * model_count + 4))
        ytick_fontsize = max(12, min(25, 28 - model_count * 0.35))
        value_fontsize = max(10, min(25, 26 - model_count * 0.28))
        xlabel_fontsize = 24 if model_count > 20 else 28
        ylabel_fontsize = 24 if model_count > 20 else 28
        title_fontsize = 18 if model_count > 20 else 20
        left_margin = 0.42 if model_count > 18 else 0.25
        
        # 设置绘图风格
        fig, ax = plt.subplots(figsize=(16, figure_height), dpi=100)
        colors = plt.get_cmap('coolwarm_r')(np.linspace(0.1, 0.9, len(plot_df)))
        
        # 绘制背景进度条
        ax.barh(plot_df['Model'], [100]*len(plot_df),
                color="#FAFAFA", edgecolor='none', height=0.7)
        
        # 绘制真实的得分条
        bars = ax.barh(plot_df['Model'], plot_df['Score'],
                       color=colors, edgecolor='none', height=0.7)
        
        # 添加数值标签 (保留两位小数)
        for bar in bars:
            width = bar.get_width()
            ax.text(width + 1.5, bar.get_y() + bar.get_height()/2.,
                    f'{width:.2f}', ha='left', va='center',
                    fontsize=value_fontsize, fontweight='bold', color='#444444')
        
        # 移除边框
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis='both', which='both', length=0)
        
        # 细节美化
        ax.set_xlabel(metric_display_name, fontsize=xlabel_fontsize, fontweight='bold', labelpad=5, 
                      x=0.32, horizontalalignment='center')
        plt.subplots_adjust(left=left_margin)
        ax.set_ylabel('Model', fontsize=ylabel_fontsize, labelpad=0, fontweight='bold')
        
        # 调整刻度字体
        plt.yticks(fontsize=ytick_fontsize, fontweight='bold')
        ax.set_xticks([])
        
        # 设置x轴范围，确保有足够空间显示标签
        max_score = plot_df['Score'].max()
        ax.set_xlim(0, max(100, max_score * 1.2))
        
        
        # 构建标题，包含筛选信息
        # 只有当有筛选条件时才显示筛选信息
        filter_parts = []
        if model_filter and model_filter.strip():
            filter_parts.append(f'Model: {model_filter}')
        if open_source_filter and open_source_filter != "All":
            filter_parts.append(f'Source: {open_source_filter}')
        if year_filter and year_filter != "All":
            filter_parts.append(f'Year: {year_filter}')
        
        if filter_parts:
            # 构建标题字符串
            filter_str = f"[{', '.join(filter_parts)}]"
            
            total_length = len(f"{metric_display_name} Leaderboard {filter_str}")
            
            if total_length > 50:
                # 第一行：主标题和排序方式
                first_line = f"{metric_display_name} Leaderboard"
                # 第二行：筛选条件
                second_line = f"[{', '.join(filter_parts)}]"
                title = f"{first_line}\n{second_line}"
            else:
                title = f"{metric_display_name} Leaderboard [{', '.join(filter_parts)}]"
        else:
            title = f"{metric_display_name} Leaderboard"
        
        ax.set_title(title, 
                     fontsize=title_fontsize, 
                     fontweight='bold', 
                     pad=30,  # 增加上边距
                     x=0.32,  # 使用与x轴标签相同的x坐标
                     horizontalalignment='center',  # 水平居中
                     y=1.05)  # 稍微向上移动一点，避免与图表太近
        
        # 调整整体布局
        plt.tight_layout()
        
        return fig
