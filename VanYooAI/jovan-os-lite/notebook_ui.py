from IPython.display import display, HTML, Markdown


def show_workflow(steps, title="Jovan OS Workflow"):
    boxes = ""

    for i, step in enumerate(steps):
        boxes += f"""
        <div style="
            border: 2px solid #111;
            color: #111;
            background: #fff;
            padding: 14px 18px;
            margin: 8px auto;
            width: 420px;
            text-align: center;
            font-family: Arial, sans-serif;
            font-size: 16px;
            font-weight: 600;
            border-radius: 4px;
        ">
            {i+1}. {step}
        </div>
        """

        if i < len(steps) - 1:
            boxes += """
            <div style="
                text-align: center;
                font-size: 28px;
                color: #111;
                line-height: 24px;
            ">
                ↓
            </div>
            """

    html = f"""
    <div style="
        margin: 20px 0;
        padding: 12px;
        background: #fff;
    ">
        <h2 style="
            text-align:center;
            color:#111;
            font-family: Arial, sans-serif;
        ">
            {title}
        </h2>
        {boxes}
    </div>
    """

    display(HTML(html))


def show_markdown(title, markdown_text):
    display(HTML(f"""
    <h2 style="
        color:#111;
        font-family: Arial, sans-serif;
        border-bottom: 2px solid #111;
        padding-bottom: 6px;
    ">
        {title}
    </h2>
    """))
    display(Markdown(markdown_text))

#def show_metric(title, value):