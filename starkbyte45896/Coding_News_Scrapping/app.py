import sys
import glob

# Try to find the actual Web_scrapper file regardless of case
scrapper_file = glob.glob('*scrapper*.py', recursive=False)
if scrapper_file:
    module_name = scrapper_file[0][:-3]
    import importlib
    app = importlib.import_module(module_name).app
else:
    from flask import Flask
    app = Flask(__name__)
    @app.route("/")
    def index():
        return "Could not find Web_scrapper.py!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860)
