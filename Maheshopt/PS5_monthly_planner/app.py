import os
from PS5MonthlyPlanner import demo


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT", os.getenv("PORT", "7860")))
    demo.launch(server_name="0.0.0.0", server_port=port, share=False)
