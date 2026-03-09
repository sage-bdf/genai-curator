# This deliverable is considered developed content as defined in contract between BDF parties.


"""Visualization module for evaluation metrics."""

from typing import Dict

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_stage_scatter(stage_metrics: Dict[str, Dict]) -> go.Figure:
    """Create a scatter plot visualization of stage performance.

    Args:
        stage_metrics: Dictionary mapping stage names to their metrics

    Returns:
        Plotly figure
    """
    stages = list(stage_metrics.keys())
    corrections = [m["corrections"] for m in stage_metrics.values()]
    accuracies = [m["correction_accuracy"] for m in stage_metrics.values()]

    # Create scatter plot with bubble size based on corrections
    fig = go.Figure(
        data=[
            go.Scatter(
                x=list(range(len(stages))),  # Stage order
                y=accuracies,
                mode="markers+text",
                marker=dict(
                    size=[c / 5 + 20 for c in corrections],  # Scale bubble size
                    sizemode="area",
                    color=corrections,
                    colorscale="Viridis",
                    showscale=True,
                    colorbar=dict(title="Number of Corrections"),
                ),
                text=stages,
                textposition="top center",
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    + "Accuracy: %{y:.1%}<br>"
                    + "Corrections: %{marker.color}<br>"
                    + "<extra></extra>"
                ),
            )
        ]
    )

    fig.update_layout(
        title="Stage Performance Overview",
        xaxis=dict(
            title="Stage Order",
            ticktext=stages,
            tickvals=list(range(len(stages))),
            tickmode="array",
        ),
        yaxis=dict(title="Correction Accuracy", tickformat=".0%", range=[0, 1]),
        showlegend=False,
        template="plotly_white",
    )
    return fig


def plot_stage_metrics(stage_metrics: Dict[str, Dict]) -> Dict[str, go.Figure]:
    """Create visualizations for stage metrics.

    Args:
        stage_metrics: Dictionary mapping stage names to their metrics

    Returns:
        Dictionary of plotly figures
    """
    stages = list(stage_metrics.keys())
    corrections = [m["corrections"] for m in stage_metrics.values()]
    accuracies = [m["correction_accuracy"] for m in stage_metrics.values()]
    rates = [m["correction_rate"] for m in stage_metrics.values()]

    # Corrections by stage
    corrections_fig = go.Figure(
        data=[
            go.Bar(
                x=stages,
                y=corrections,
                text=corrections,
                textposition="auto",
            )
        ]
    )
    corrections_fig.update_layout(
        title="Corrections by Stage",
        xaxis_title="Stage",
        yaxis_title="Number of Corrections",
        template="plotly_white",
    )

    # Correction accuracy by stage
    accuracy_fig = go.Figure(
        data=[
            go.Bar(
                x=stages,
                y=accuracies,
                text=[f"{a:.1%}" for a in accuracies],
                textposition="auto",
            )
        ]
    )
    accuracy_fig.update_layout(
        title="Correction Accuracy by Stage",
        xaxis_title="Stage",
        yaxis_title="Accuracy",
        yaxis=dict(tickformat=".0%", range=[0, 1]),  # Set y-axis range for percentages
        template="plotly_white",
    )

    # Correction rate by stage
    rate_fig = go.Figure(
        data=[
            go.Bar(
                x=stages,
                y=rates,
                text=[f"{r:.1%}" for r in rates],
                textposition="auto",
            )
        ]
    )
    rate_fig.update_layout(
        title="Correction Rate by Stage",
        xaxis_title="Stage",
        yaxis_title="Rate",
        yaxis=dict(tickformat=".0%", range=[0, 1]),  # Set y-axis range for percentages
        template="plotly_white",
    )

    # Create scatter plot
    scatter_fig = plot_stage_scatter(stage_metrics)

    return {
        "corrections": corrections_fig,
        "accuracy": accuracy_fig,
        "rate": rate_fig,
        "scatter": scatter_fig,
    }


def plot_field_correction_summary(field_metrics: Dict[str, Dict]) -> go.Figure:
    """Create a summary bar chart of correction accuracy by field.

    Args:
        field_metrics: Dictionary mapping field names to their metrics

    Returns:
        Plotly figure showing correction accuracy for each field
    """
    # Extract and sort fields by accuracy
    fields = []
    accuracies = []
    error_counts = []

    for field, metrics in field_metrics.items():
        fields.append(field)
        accuracies.append(metrics["correction_accuracy"])
        error_counts.append(metrics["corrections"])

    # Sort by accuracy
    sorted_indices = np.argsort(accuracies)
    fields = [fields[i] for i in sorted_indices]
    accuracies = [accuracies[i] for i in sorted_indices]
    error_counts = [error_counts[i] for i in sorted_indices]

    # Create simple bar chart
    fig = go.Figure(
        data=[
            go.Bar(
                x=fields,
                y=accuracies,
                text=[f"{a:.1%}" for a in accuracies],
                textposition="auto",
            )
        ]
    )

    # Use same clean style as base accuracy chart
    fig.update_layout(
        title="Correction Accuracy by Field",
        xaxis_title="Field",
        yaxis_title="Correction Accuracy",
        yaxis=dict(tickformat=".0%", range=[0, 1]),
        template="plotly_white",
    )

    return fig


def plot_field_metrics(field_metrics: Dict[str, Dict]) -> Dict[str, go.Figure]:
    """Create visualizations for field metrics.

    Args:
        field_metrics: Dictionary mapping field names to their metrics

    Returns:
        Dictionary of plotly figures
    """
    fields = list(field_metrics.keys())
    base_accuracies = [m["base_accuracy"] for m in field_metrics.values()]
    corrections = [m["corrections"] for m in field_metrics.values()]
    accuracies = [m["correction_accuracy"] for m in field_metrics.values()]
    rates = [m["correction_rate"] for m in field_metrics.values()]

    # Create heatmap data
    heatmap_data = pd.DataFrame(
        {
            "Field": fields,
            "Base Accuracy": base_accuracies,
            "Corrections": corrections,
            "Correction Accuracy": accuracies,
            "Correction Rate": rates,
        }
    ).set_index("Field")

    # Heatmap of all metrics
    heatmap_fig = px.imshow(
        heatmap_data,
        aspect="auto",
        color_continuous_scale="RdYlGn",
        labels={"color": "Value"},
    )
    # Update color scale range for percentage values
    heatmap_fig.update_traces(
        zmin=0, zmax=1, showscale=True, colorbar={"title": "Value", "ticksuffix": "%"}
    )
    heatmap_fig.update_layout(title="Field Performance Matrix", template="plotly_white")

    # Base accuracy by field
    base_accuracy_fig = go.Figure(
        data=[
            go.Bar(
                x=fields,
                y=base_accuracies,
                text=[f"{a:.1%}" for a in base_accuracies],
                textposition="auto",
            )
        ]
    )
    base_accuracy_fig.update_layout(
        title="Base Accuracy by Field",
        xaxis_title="Field",
        yaxis_title="Base Accuracy",
        yaxis=dict(tickformat=".0%", range=[0, 1]),  # Set y-axis range for percentages
        template="plotly_white",
    )

    # Corrections by field
    corrections_fig = go.Figure(
        data=[
            go.Bar(
                x=fields,
                y=corrections,
                text=corrections,
                textposition="auto",
            )
        ]
    )
    corrections_fig.update_layout(
        title="Corrections by Field",
        xaxis_title="Field",
        yaxis_title="Number of Corrections",
        template="plotly_white",
    )

    # Scatter plot of accuracy vs corrections
    scatter_fig = go.Figure(
        data=[
            go.Scatter(
                x=corrections,
                y=accuracies,
                mode="markers+text",
                text=fields,
                textposition="top center",
            )
        ]
    )
    scatter_fig.update_layout(
        title="Correction Accuracy vs Number of Corrections",
        xaxis_title="Number of Corrections",
        yaxis_title="Correction Accuracy",
        yaxis=dict(tickformat=".0%", range=[0, 1]),  # Set y-axis range for percentages
        template="plotly_white",
    )

    # Create correction summary
    summary_fig = plot_field_correction_summary(field_metrics)

    return {
        "heatmap": heatmap_fig,
        "base_accuracy": base_accuracy_fig,
        "corrections": corrections_fig,
        "scatter": scatter_fig,
        "summary": summary_fig,
    }


def plot_evaluation_metrics(metrics: Dict) -> Dict[str, go.Figure]:
    """Create visualizations for overall evaluation metrics.

    Args:
        metrics: Overall evaluation metrics

    Returns:
        Dictionary of plotly figures
    """
    # Gauge charts for accuracies and rates
    gauge_figs = {}

    # Base accuracy gauge
    gauge_figs["base_accuracy"] = go.Figure(
        data=[
            go.Indicator(
                mode="gauge+number",
                value=metrics["base_accuracy"]
                * 100,  # Convert to percentage for display
                title={"text": "Base Accuracy"},
                number={"suffix": "%", "valueformat": ".1f"},  # Show as percentage
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "darkblue"},
                    "steps": [
                        {"range": [0, 50], "color": "red"},
                        {"range": [50, 80], "color": "yellow"},
                        {"range": [80, 100], "color": "green"},
                    ],
                },
            )
        ]
    )

    # Correction accuracy gauge
    gauge_figs["correction_accuracy"] = go.Figure(
        data=[
            go.Indicator(
                mode="gauge+number",
                value=metrics["correction_accuracy"]
                * 100,  # Convert to percentage for display
                title={"text": "Correction Accuracy"},
                number={"suffix": "%", "valueformat": ".1f"},  # Show as percentage
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "darkblue"},
                    "steps": [
                        {"range": [0, 50], "color": "red"},
                        {"range": [50, 80], "color": "yellow"},
                        {"range": [80, 100], "color": "green"},
                    ],
                },
            )
        ]
    )

    # Correction rate gauge
    gauge_figs["correction_rate"] = go.Figure(
        data=[
            go.Indicator(
                mode="gauge+number",
                value=metrics["correction_rate"]
                * 100,  # Convert to percentage for display
                title={"text": "Correction Rate"},
                number={"suffix": "%", "valueformat": ".1f"},  # Show as percentage
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "darkblue"},
                    "steps": [
                        {"range": [0, 50], "color": "red"},
                        {"range": [50, 80], "color": "yellow"},
                        {"range": [80, 100], "color": "green"},
                    ],
                },
            )
        ]
    )

    # Big number for total corrections
    total_corrections_fig = go.Figure(
        data=[
            go.Indicator(
                mode="number",
                value=metrics["total_corrections"],
                title={"text": "Total Corrections"},
            )
        ]
    )

    return {**gauge_figs, "total_corrections": total_corrections_fig}


def save_visualizations(
    figures: Dict[str, go.Figure], output_dir: str, prefix: str = ""
) -> None:
    """Save plotly figures as HTML files.

    Args:
        figures: Dictionary of figures to save
        output_dir: Directory to save figures in
        prefix: Optional prefix for filenames
    """
    import os

    os.makedirs(output_dir, exist_ok=True)

    for name, fig in figures.items():
        filename = f"{prefix}_{name}.html" if prefix else f"{name}.html"
        filepath = os.path.join(output_dir, filename)
        fig.write_html(filepath)
